"""Operation-scoped coverage for a trusted, single-process teaching model.

This composes the evidence model in change_control.py with scoped activation.
The route inventory, requirement policy and evaluator-scope registry are trusted
inputs, not facts inferred by the gate. No remote authorization is implemented.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Mapping

from change_control import (Authority, Claim, ClaimAssessment, Controller, Snapshot,
                            Verdict, assess, digest_object, run_check, _module)


@dataclass(frozen=True)
class RouteSpec:
    id: str
    conditions: tuple[str, ...]


@dataclass(frozen=True)
class CoverageBinding:
    route: str
    condition: str
    claim_id: str
    claim_ref: str


@dataclass(frozen=True)
class CoveragePolicy:
    revision: int
    routes: tuple[RouteSpec, ...]
    bindings: tuple[CoverageBinding, ...]
    # A discovered but unclassified route is NOT silently treated as irrelevant.
    open_discoveries: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ids = [r.id for r in self.routes]
        if self.revision < 1 or not ids or len(set(ids)) != len(ids):
            raise ValueError("nonempty, unique route inventory and positive revision required")
        if any(not r.id or not r.conditions or any(not c for c in r.conditions)
               or len(set(r.conditions)) != len(r.conditions) for r in self.routes):
            raise ValueError("each route needs distinct, nonempty conditions")
        pairs = [(b.route, b.condition) for b in self.bindings]
        if len(set(pairs)) != len(pairs):
            raise ValueError("ambiguous duplicate coverage binding")
        requirements = {(r.id, c) for r in self.routes for c in r.conditions}
        if any(pair not in requirements for pair in pairs):
            raise ValueError("binding outside declared requirements")

    @property
    def ref(self) -> str:
        return digest_object(asdict_json(self))


@dataclass(frozen=True)
class RouteView:
    """Trusted local route observation. None means unobserved, not disabled."""
    epoch: int
    modes: tuple[tuple[str, bool | None], ...]
    observed: bool = True
    environment: str = "staging"
    tenants: tuple[str, ...] = ("tenant-a",)

    def __post_init__(self) -> None:
        names = [name for name, _ in self.modes]
        if self.epoch < 1 or len(names) != len(set(names)):
            raise ValueError("invalid route observation")
        if any(type(value) not in (bool, type(None)) for _, value in self.modes):
            raise ValueError("route mode must be bool or None")


@dataclass(frozen=True)
class RuntimeObservation:
    """What a trusted observer reports, not permission to load this artifact.

    The local executor can make an immediate observation of its own update.
    A remote adapter would need its own authenticity and freshness contract.
    """
    epoch: int
    snapshot_ref: str | None
    release_generation: int
    observed: bool = True
    environment: str = "staging"
    tenants: tuple[str, ...] = ("tenant-a",)

    def __post_init__(self) -> None:
        if (type(self.epoch) is not int or self.epoch < 1
                or type(self.release_generation) is not int or self.release_generation < 0
                or type(self.observed) is not bool or not self.environment
                or not self.tenants or len(set(self.tenants)) != len(self.tenants)):
            raise ValueError("invalid runtime observation")

    @property
    def ref(self) -> str:
        return digest_object(asdict_json(self))


@dataclass(frozen=True)
class ScopedOperation:
    # Complete post-operation enabled route set; implicit disabling is prohibited.
    enabled_routes: tuple[str, ...]
    environment: str = "staging"
    tenants: tuple[str, ...] = ("tenant-a",)
    action: str = "activate"


@dataclass(frozen=True)
class CoverageDecision:
    verdict: Verdict
    operation: ScopedOperation
    snapshot_ref: str
    policy_ref: str
    registry_ref: str
    authority_epoch: int
    state_epoch: int
    route_epoch: int
    route_view_ref: str
    active_snapshot_ref: str | None
    release_generation: int
    runtime_observation_ref: str
    required: tuple[tuple[str, str], ...]
    covered: tuple[tuple[str, str], ...]
    assessments: tuple[ClaimAssessment, ...]
    reasons: tuple[str, ...]


def asdict_json(value: object) -> dict:
    # Dataclass tuple fields become arrays for the legacy integer-only encoder.
    import json
    return json.loads(json.dumps(asdict(value), ensure_ascii=False))


class ScopedController:
    """Only local activation is modeled. All observations share one local lock.

    approved_scopes records the reviewed meaning of each evaluator. Merely
    adding a row to coverage bindings cannot expand that meaning. Changing the
    registry itself is trusted configuration, NOT a privilege of an agent.
    """
    def __init__(self, snapshot: Snapshot, claims: tuple[Claim, ...],
                 policy: CoveragePolicy, view: RouteView,
                 approved_scopes: Mapping[str, tuple[tuple[str, str], ...]],
                 authority: Authority | None = None) -> None:
        if len({c.id for c in claims}) != len(claims):
            raise ValueError("duplicate claim id")
        self.core = Controller(snapshot, claims, authority or Authority(actions=("activate",)))
        self.policy = policy
        self.view = view
        self._scopes = tuple(sorted((k, tuple(sorted(v))) for k, v in approved_scopes.items()))
        self.registry_ref = digest_object({k: [list(p) for p in v] for k, v in self._scopes})
        self.receipts: list[dict] = []
        self.operations: dict[str, tuple[str, str]] = {}
        self.effect_count = 0
        # Only execute() can replace the admitted running artifact through this API.
        # Controller.snapshot remains the candidate used for evidence evaluation.
        self._active_snapshot: Snapshot | None = None
        self._active_operation: ScopedOperation | None = None
        self._release_generation = 0
        self.runtime_observation = RuntimeObservation(
            1, None, 0, environment=view.environment, tenants=view.tenants)
        self.runtime_history: list[dict] = [asdict_json(self.runtime_observation)]

    @property
    def candidate_snapshot(self) -> Snapshot:
        return self.core.snapshot

    @property
    def active_snapshot(self) -> Snapshot | None:
        return self._active_snapshot

    @property
    def release_generation(self) -> int:
        return self._release_generation

    def observe_candidate(self, snapshot: Snapshot) -> None:
        """Update the candidate and invalidate decisions, never the running code."""
        self.core.observe(snapshot)

    def observe(self, snapshot: Snapshot) -> None:
        """Compatibility alias for observe_candidate(), not a deployment API."""
        self.observe_candidate(snapshot)

    def observe_runtime(self, observation: RuntimeObservation) -> None:
        """Record runtime facts without approving or loading the reported code.

        A mismatch or an unavailable observation blocks the local invocation
        gate. A later matching observation can clear that local containment;
        it does not prove that remote effects or data have been repaired.
        """
        with self.core._lock:
            if observation.epoch <= self.runtime_observation.epoch:
                raise ValueError("runtime observation epoch must increase")
            self.runtime_observation = observation
            self.runtime_history.append(asdict_json(observation))
            self.core.state_epoch += 1

    def _runtime_issue(self) -> str | None:
        observation = self.runtime_observation
        if not observation.observed:
            return "runtime_unobserved"
        expected_ref = self._active_snapshot.fingerprint if self._active_snapshot else None
        if (observation.snapshot_ref != expected_ref
                or observation.release_generation != self._release_generation):
            return "runtime_artifact_mismatch"
        expected_environment = (self._active_operation.environment if self._active_operation
                                else self.view.environment)
        expected_tenants = (self._active_operation.tenants if self._active_operation
                            else self.view.tenants)
        if (observation.environment != expected_environment
                or set(observation.tenants) != set(expected_tenants)):
            return "runtime_observation_scope_mismatch"
        if self._active_operation is not None:
            if (self.view.environment != expected_environment
                    or set(self.view.tenants) != set(expected_tenants)):
                return "active_route_scope_mismatch"
            observed_enabled = {name for name, enabled in self.view.modes if enabled is True}
            if observed_enabled != set(self._active_operation.enabled_routes):
                return "runtime_route_mismatch"
        elif any(enabled is True for _, enabled in self.view.modes):
            return "runtime_routes_without_admitted_artifact"
        return None

    def observe_routes(self, view: RouteView) -> None:
        with self.core._lock:
            if view.epoch <= self.view.epoch:
                raise ValueError("route observation epoch must increase")
            self.view = view
            self.core.state_epoch += 1

    def update_policy(self, policy: CoveragePolicy, claims: tuple[Claim, ...] | None = None) -> None:
        # Trusted test driver only; not an external policy-update API.
        with self.core._lock:
            if policy.revision <= self.policy.revision:
                raise ValueError("policy revision must increase")
            if claims is not None:
                if len({c.id for c in claims}) != len(claims):
                    raise ValueError("duplicate claim id")
                self.core.claims = claims
            self.policy = policy
            self.core.state_epoch += 1

    def _binding(self, route: str, condition: str) -> tuple[Claim | None, str | None]:
        item = next((b for b in self.policy.bindings
                     if (b.route, b.condition) == (route, condition)), None)
        if item is None:
            return None, "coverage_missing"
        claim = next((c for c in self.core.claims if c.id == item.claim_id), None)
        if claim is None:
            return None, "claim_missing"
        if item.claim_ref != claim.ref:
            return None, "coverage_binding_stale"
        if (route, condition) not in dict(self._scopes).get(claim.checker, ()):
            return None, "evaluator_scope_mismatch"
        return claim, None

    def decide(self, op: ScopedOperation) -> CoverageDecision:
        with self.core._lock:
            deny: list[str] = []
            hold: list[str] = []
            runtime_issue = self._runtime_issue()
            if runtime_issue:
                hold.append(runtime_issue)
            desired = set(op.enabled_routes)
            known = {r.id for r in self.policy.routes}
            current = dict(self.view.modes)
            if op.action != "activate" or not desired or len(desired) != len(op.enabled_routes):
                deny.append("invalid_activation_scope")
            if not desired.issubset(known):
                deny.append("undeclared_requested_route")
            if not self.view.observed or known != set(current) or any(v is None for v in current.values()):
                hold.append("route_observation_incomplete")
            if (op.environment != self.view.environment or set(op.tenants) != set(self.view.tenants)):
                hold.append("route_observation_scope_mismatch")
            active = {k for k, v in current.items() if v is True}
            if not active.issubset(desired):
                deny.append("implicit_disable_not_supported")
            if self.policy.open_discoveries:
                hold.extend("discovery_unresolved:" + x for x in self.policy.open_discoveries)
            a = self.core.authority
            if not a.observed:
                hold.append("authority_unobserved")
            elif not a.enabled:
                deny.append("authority_revoked")
            elif (op.action not in a.actions or op.environment not in a.environments
                  or not op.tenants or not set(op.tenants).issubset(a.tenants)):
                deny.append("operation_outside_authority")
            required = tuple(sorted((r.id, c) for r in self.policy.routes
                                    if r.id in (desired | active) for c in r.conditions))
            covered = []
            views: dict[str, ClaimAssessment] = {}
            for route, condition in required:
                claim, issue = self._binding(route, condition)
                if issue:
                    hold.append(f"{issue}:{route}:{condition}")
                    continue
                assert claim is not None
                covered.append((route, condition))
                views[claim.id] = assess(self.core.snapshot, claim, self.core.records)
            for v in views.values():
                if v.status == "CONTRADICTED":
                    deny.append(v.claim_id + ":counterexample")
                elif v.status != "CURRENT":
                    hold.append(v.claim_id + ":" + v.status.lower())
            verdict: Verdict = "DENY" if deny else "HOLD" if hold else "ALLOW"
            return CoverageDecision(verdict, op, self.core.snapshot.fingerprint,
                self.policy.ref, self.registry_ref, a.epoch, self.core.state_epoch,
                self.view.epoch, digest_object(asdict_json(self.view)),
                self._active_snapshot.fingerprint if self._active_snapshot else None,
                self._release_generation, self.runtime_observation.ref, required,
                tuple(covered), tuple(views.values()), tuple(deny + hold))

    def revalidate(self, op: ScopedOperation) -> int:
        with self.core._lock:
            required = self.decide(op).required
            selected: dict[str, Claim] = {}
            for route, condition in required:
                claim, issue = self._binding(route, condition)
                if claim is not None and issue is None:
                    selected[claim.id] = claim
            count = 0
            for claim in selected.values():
                if assess(self.core.snapshot, claim, self.core.records).status in ("CURRENT", "CONTRADICTED"):
                    continue
                try:
                    record = run_check(self.core.snapshot, claim, len(self.core.records) + 1)
                except (LookupError, KeyError):
                    continue
                self.core.records += (record,)
                self.core.check_runs += 1
                self.core.state_epoch += 1
                count += 1
            return count

    def execute(self, decision: CoverageDecision, key: str) -> dict:
        if not key:
            raise ValueError("operation id required")
        with self.core._lock:
            intent = digest_object({"snapshot": decision.snapshot_ref,
                                    "operation": asdict_json(decision.operation)})
            if key in self.operations:
                old_intent, status = self.operations[key]
                if old_intent != intent:
                    raise ValueError("operation id already used for a different intent")
                return {"status": "already_completed", "effect_executed": False}
            current = self.decide(decision.operation)
            if decision.verdict != "ALLOW":
                return {"status": "not_admitted", "effect_executed": False}
            if current.verdict != "ALLOW":
                return {"status": current.verdict.lower(), "effect_executed": False,
                        "reasons": list(current.reasons)}
            fields = ("snapshot_ref", "policy_ref", "registry_ref", "authority_epoch",
                      "state_epoch", "route_epoch", "route_view_ref", "active_snapshot_ref",
                      "release_generation", "runtime_observation_ref")
            if any(getattr(decision, f) != getattr(current, f) for f in fields):
                return {"status": "hold", "effect_executed": False, "reasons": ["decision_stale"]}
            desired = set(decision.operation.enabled_routes)
            prior_active = self._active_snapshot.fingerprint if self._active_snapshot else None
            # Evaluation and publication of the admitted artifact occur under
            # the same LOCAL lock. Candidate observation is never publication.
            self._active_snapshot = self.candidate_snapshot
            self._active_operation = decision.operation
            self._release_generation += 1
            self.view = replace(self.view, epoch=self.view.epoch + 1,
                modes=tuple((r.id, r.id in desired) for r in self.policy.routes))
            self.runtime_observation = RuntimeObservation(
                self.runtime_observation.epoch + 1, self._active_snapshot.fingerprint,
                self._release_generation, environment=decision.operation.environment,
                tenants=decision.operation.tenants)
            self.runtime_history.append(asdict_json(self.runtime_observation))
            self.core.state_epoch += 1
            self.operations[key] = (intent, "succeeded")
            self.effect_count += 1
            receipt = {"status": "succeeded", "effect_executed": True, "intent_ref": intent,
                       "enabled_routes": sorted(desired), "decision": asdict_json(current),
                       "previous_active_ref": prior_active,
                       "active_snapshot_ref": self._active_snapshot.fingerprint,
                       "release_generation": self._release_generation}
            self.receipts.append(receipt)
            return receipt

    def invoke_demo_route(self, route: str, actor: dict, row: dict) -> bool:
        """Actual local gate enforcement, not a caller-supplied 'disabled' label.

        Only the two teaching routes are executable here. Synthetic route
        discovery and policy expansion do not create a real gateway service.
        """
        with self.core._lock:
            if (self._active_snapshot is None or self._active_operation is None
                    or self._runtime_issue() is not None
                    or not self.view.observed
                    or any(mode is None for _, mode in self.view.modes)
                    or route not in self._active_operation.enabled_routes
                    or dict(self.view.modes).get(route) is not True
                    or actor.get("tenant") not in self._active_operation.tenants):
                return False
            functions = {"api": ("app.py", "can_export"),
                         "batch": ("batch.py", "can_export_batch")}
            if route not in functions:
                raise ValueError("route not implemented by local teaching gateway")
            resource, name = functions[route]
            return _module(self._active_snapshot, resource)[name](actor, row) is True
