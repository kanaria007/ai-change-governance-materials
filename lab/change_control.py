"""Executable teaching model. Not a production authorization or sandbox service.

All fixture code is authored locally and trusted. Never load untrusted PR code
in this process. The critical section protects a simulated local deployment
pointer, not a remote deployment system. Evidence history is append-only only
through this API; it is neither durable nor cryptographically authenticated.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import inspect
import json
import platform
from threading import RLock
from typing import Callable, Literal, Mapping

Outcome = Literal["PASS", "FAIL", "ERROR"]
Support = Literal["CURRENT", "STALE", "UNKNOWN", "CONTRADICTED"]
Verdict = Literal["ALLOW", "HOLD", "DENY"]


def digest_bytes(value: str) -> str:
    return "sha256:" + sha256(value.encode("utf-8")).hexdigest()


def stable_json(value: object) -> str:
    """Local lab-json-v1: sorted string keys, UTF-8, no floats. Not RFC JCS."""
    def validate(v: object) -> None:
        if v is None or type(v) in (str, int, bool):
            return
        if type(v) is list:
            for x in v:
                validate(x)
            return
        if type(v) is dict and all(type(k) is str for k in v):
            for x in v.values():
                validate(x)
            return
        raise TypeError(f"Unsupported lab-json-v1 value: {type(v).__name__}")
    validate(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_object(value: object) -> str:
    return digest_bytes(stable_json(value))


@dataclass(frozen=True)
class Snapshot:
    # A tuple, rather than a mutable dictionary, fixes this observation.
    resources: tuple[tuple[str, str | None], ...]

    @classmethod
    def of(cls, resources: Mapping[str, str | None]) -> Snapshot:
        return cls(tuple(sorted(resources.items())))

    def read(self, name: str) -> str:
        values = dict(self.resources)
        if name not in values or values[name] is None:
            raise LookupError(f"Unobserved resource: {name}")
        return values[name]  # type: ignore[return-value]

    def with_changes(self, **resources: str | None) -> Snapshot:
        return Snapshot.of(dict(self.resources) | resources)

    @property
    def fingerprint(self) -> str:
        return digest_object({name: None if body is None else digest_bytes(body)
                              for name, body in self.resources})


@dataclass(frozen=True)
class Claim:
    id: str
    statement: str
    dependencies: tuple[str, ...]
    checker: str

    @property
    def ref(self) -> str:
        return digest_object({"id": self.id, "statement": self.statement,
                              "dependencies": list(self.dependencies),
                              "checker": self.checker})


@dataclass(frozen=True)
class EvidenceRecord:
    sequence: int
    claim_id: str
    claim_ref: str
    bindings: tuple[tuple[str, str], ...]
    outcome: Outcome
    detail: str


@dataclass(frozen=True)
class ClaimAssessment:
    claim_id: str
    status: Support
    evidence_sequences: tuple[int, ...]
    reason: str


# These two functions intentionally execute only trusted, local teaching code.
def _module(snapshot: Snapshot, name: str) -> dict:
    namespace: dict = {}
    exec(compile(snapshot.read(name), name, "exec"), namespace)
    return namespace


def _json(snapshot: Snapshot, name: str) -> object:
    return json.loads(snapshot.read(name))


def check_tenant(snapshot: Snapshot) -> tuple[bool, str]:
    allowed = _module(snapshot, "app.py")["can_export"]
    cases = _json(snapshot, "tenant_cases.json")
    for case in cases:  # type: ignore[union-attr]
        actual = allowed(case["actor"], case["row"])
        if actual is not case["expected"]:
            return False, "tenant isolation counterexample: " + case["name"]
    return True, "all declared tenant cases passed"


def check_wire(snapshot: Snapshot) -> tuple[bool, str]:
    encode = _module(snapshot, "wire.py")["encode"]
    visible = _module(snapshot, "client.py")["visible"]
    for expected in (True, False):
        observed = visible(encode(expected))
        if observed is not expected:
            return False, "explicit false did not survive the declared route"
    return True, "both boolean values survived server-to-client serialization"


def check_storage(snapshot: Snapshot) -> tuple[bool, str]:
    render = _module(snapshot, "app.py")["render"]
    data = _json(snapshot, "data.json")
    try:
        actual = render(data["row"])  # type: ignore[index]
    except (KeyError, TypeError) as exc:
        # The contract explicitly classifies failure to render this valid row
        # as a counterexample, rather than treating every runner error as FAIL.
        return False, "declared storage compatibility counterexample: " + type(exc).__name__
    return (actual == "sample", "declared stored row rendered" if actual == "sample"
            else "declared stored row has wrong output")


def check_batch(snapshot: Snapshot) -> tuple[bool, str]:
    allowed = _module(snapshot, "batch.py")["can_export_batch"]
    for case in _json(snapshot, "tenant_cases.json"):  # type: ignore[union-attr]
        if allowed(case["actor"], case["row"]) is not case["expected"]:
            return False, "batch isolation counterexample: " + case["name"]
    return True, "all declared batch tenant cases passed"


CHECKERS: dict[str, Callable[[Snapshot], tuple[bool, str]]] = {
    "tenant-v1": check_tenant, "wire-v1": check_wire,
    "storage-v1": check_storage, "batch-v1": check_batch,
}


def checker_ref(claim: Claim) -> str:
    # Pin the helper implementations as well as the named evaluator.
    source = inspect.getsource(CHECKERS[claim.checker])
    source += inspect.getsource(_module) + inspect.getsource(_json)
    return digest_bytes(source)


def context_for(snapshot: Snapshot, claim: Claim) -> tuple[tuple[str, str], ...]:
    values = {name: digest_bytes(snapshot.read(name)) for name in claim.dependencies}
    values["@claim"] = claim.ref
    values["@checker"] = checker_ref(claim)
    values["@python"] = digest_bytes(platform.python_implementation() + platform.python_version())
    # Explicit observation of a lab environment profile is required.
    values["@environment"] = digest_bytes(snapshot.read("environment.json"))
    return tuple(sorted(values.items()))


def run_check(snapshot: Snapshot, claim: Claim, sequence: int) -> EvidenceRecord:
    bindings = context_for(snapshot, claim)
    try:
        ok, detail = CHECKERS[claim.checker](snapshot)
        outcome: Outcome = "PASS" if ok else "FAIL"
    except Exception as exc:
        outcome, detail = "ERROR", "runner error: " + type(exc).__name__
    return EvidenceRecord(sequence, claim.id, claim.ref, bindings, outcome, detail)


def assess(snapshot: Snapshot, claim: Claim,
           evidence: tuple[EvidenceRecord, ...]) -> ClaimAssessment:
    try:
        expected = context_for(snapshot, claim)
    except (LookupError, KeyError):
        return ClaimAssessment(claim.id, "UNKNOWN", (), "required observation is unavailable")
    history = [e for e in evidence if e.claim_id == claim.id]
    applicable = [e for e in history if e.claim_ref == claim.ref and e.bindings == expected]
    sequences = tuple(e.sequence for e in applicable)
    if any(e.outcome == "FAIL" for e in applicable):
        # A passing retry cannot silently erase a counterexample for this context.
        return ClaimAssessment(claim.id, "CONTRADICTED", sequences, "applicable counterexample exists")
    if any(e.outcome == "ERROR" for e in applicable):
        return ClaimAssessment(claim.id, "UNKNOWN", sequences, "applicable evaluation is incomplete")
    if any(e.outcome == "PASS" for e in applicable):
        return ClaimAssessment(claim.id, "CURRENT", sequences, "declared context is supported")
    if history:
        return ClaimAssessment(claim.id, "STALE", (), "historical evidence does not bind this context")
    return ClaimAssessment(claim.id, "UNKNOWN", (), "no evidence for this claim")


@dataclass(frozen=True)
class Authority:
    actor: str = "release-bot"
    enabled: bool = True
    actions: tuple[str, ...] = ("deploy",)
    environments: tuple[str, ...] = ("staging",)
    tenants: tuple[str, ...] = ("tenant-a",)
    epoch: int = 1
    observed: bool = True


@dataclass(frozen=True)
class Operation:
    action: str = "deploy"
    environment: str = "staging"
    tenants: tuple[str, ...] = ("tenant-a",)


@dataclass(frozen=True)
class GateDecision:
    verdict: Verdict
    snapshot_ref: str
    policy_ref: str
    authority_epoch: int
    state_epoch: int
    operation: Operation
    assessments: tuple[ClaimAssessment, ...]
    reasons: tuple[str, ...]


class Controller:
    """Single-process control model. No remote systems, secrets or AI calls."""
    def __init__(self, snapshot: Snapshot, claims: tuple[Claim, ...],
                 authority: Authority | None = None) -> None:
        self.snapshot = snapshot
        self.claims = claims
        self.authority = authority or Authority()
        self.records: tuple[EvidenceRecord, ...] = ()
        self.state_epoch = 1
        self.check_runs = 0
        self.effect_count = 0
        self.deployed: str | None = None
        self.operations: dict[str, tuple[str, str]] = {}
        self.audit: list[dict] = []
        self._lock = RLock()

    @property
    def policy_ref(self) -> str:
        return digest_object({"schema": "lab-gate-policy/v1", "claims": [c.ref for c in self.claims],
                              "rule": "all-current-and-current-authority", "version": 1})

    def observe(self, snapshot: Snapshot) -> None:
        with self._lock:
            self.snapshot = snapshot
            self.state_epoch += 1

    def set_authority(self, authority: Authority) -> None:
        with self._lock:
            if authority.epoch <= self.authority.epoch:
                raise ValueError("authority epochs must increase")
            self.authority = authority
            self.state_epoch += 1

    def revalidate(self, force: bool = False) -> tuple[EvidenceRecord, ...]:
        with self._lock:
            added = []
            for claim in self.claims:
                view = assess(self.snapshot, claim, self.records)
                if not force and view.status in ("CURRENT", "CONTRADICTED"):
                    continue
                try:
                    record = run_check(self.snapshot, claim, len(self.records) + 1)
                except (LookupError, KeyError):
                    # No fabricated result for an unobserved input.
                    continue
                self.records += (record,)
                added.append(record)
                self.check_runs += 1
                self.state_epoch += 1
            return tuple(added)

    def decide(self, operation: Operation | None = None) -> GateDecision:
        with self._lock:
            op = operation or Operation()
            assessments = tuple(assess(self.snapshot, c, self.records) for c in self.claims)
            deny, hold = [], []
            a = self.authority
            if not a.observed:
                hold.append("authority_unobserved")
            elif not a.enabled:
                deny.append("authority_revoked")
            elif (op.action not in a.actions or op.environment not in a.environments
                  or not op.tenants or not set(op.tenants).issubset(a.tenants)):
                deny.append("operation_outside_authority")
            if not self.claims:
                hold.append("required_claims_missing")
            for view in assessments:
                if view.status == "CONTRADICTED":
                    deny.append(view.claim_id + ":counterexample")
                elif view.status != "CURRENT":
                    hold.append(view.claim_id + ":" + view.status.lower())
            verdict: Verdict = "DENY" if deny else "HOLD" if hold else "ALLOW"
            return GateDecision(verdict, self.snapshot.fingerprint, self.policy_ref, a.epoch,
                                self.state_epoch, op, assessments, tuple(deny + hold))

    def execute(self, decision: GateDecision, key: str,
                lose_ack: bool = False) -> dict:
        """Simulate an effect under one local lock, with intent-bound deduplication.

        lose_ack models a performed effect whose completion acknowledgement is
        lost. UNKNOWN is never retried automatically. There is no durability.
        """
        if not key:
            raise ValueError("idempotency key must be nonempty")
        with self._lock:
            intent = digest_object({"snapshot": decision.snapshot_ref,
                                    "operation": {"action": decision.operation.action,
                                      "environment": decision.operation.environment,
                                      "tenants": list(decision.operation.tenants)}})
            if key in self.operations:
                prior_intent, status = self.operations[key]
                if prior_intent != intent:
                    raise ValueError("idempotency key was already bound to another intent")
                return {"status": "already_completed" if status == "succeeded" else "unknown",
                        "effect_executed": False}
            current = self.decide(decision.operation)
            if decision.verdict != "ALLOW":
                return {"status": "not_admitted", "effect_executed": False}
            if current.verdict != "ALLOW":
                return {"status": current.verdict.lower(), "reasons": list(current.reasons),
                        "effect_executed": False}
            if (decision.snapshot_ref != current.snapshot_ref
                    or decision.policy_ref != current.policy_ref
                    or decision.authority_epoch != current.authority_epoch
                    or decision.state_epoch != current.state_epoch):
                return {"status": "hold", "reasons": ["decision_stale"], "effect_executed": False}
            self.operations[key] = (intent, "in_progress")
            self.deployed = current.snapshot_ref
            self.effect_count += 1
            status = "unknown" if lose_ack else "succeeded"
            self.operations[key] = (intent, status)
            record = {"status": status, "effect_executed": True, "intent_ref": intent,
                      "snapshot_ref": current.snapshot_ref, "state_epoch": current.state_epoch,
                      "idempotency_key": key}
            self.audit.append(record)
            return record


def as_json_record(value: object) -> dict:
    return json.loads(json.dumps(asdict(value), ensure_ascii=False))  # type: ignore[arg-type]
