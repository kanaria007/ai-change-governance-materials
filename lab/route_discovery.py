"""Bounded static route discovery. Standard-library AST only; not taint analysis.

Supported surface: module-level functions, @entrypoint markers, direct calls to
module-local names. Unresolved/dynamic calls are retained as investigation work.
Every strategy receives the same source. Gold labels are never scanner inputs.
"""
from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from pathlib import Path
import re

KEYWORDS = ("export", "csv", "download")
SINKS = ("emit_document",)
SAFE_EXTERNAL = ("permitted", "len", "str", "bool", "range")
STRATEGIES = ("name", "name_callers", "effect", "union", "all_entries")


@dataclass(frozen=True)
class Discovery:
    strategy: str
    entries: tuple[str, ...]
    candidates: tuple[str, ...]
    unresolved: tuple[str, ...]
    reasons: dict[str, list[str]]
    source_bytes: int
    ast_nodes: int
    edges_examined: int
    parse_error: str | None = None


def scan(source: str, strategy: str, sinks: tuple[str, ...] = SINKS) -> Discovery:
    if strategy not in STRATEGIES:
        raise ValueError("unknown discovery strategy")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return Discovery(strategy, (), (), ("<parse-error>",), {},
                         len(source.encode()), 0, 0, f"SyntaxError at line {exc.lineno}")
    functions = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    entries = {name for name, fn in functions.items() if any(
        isinstance(d, ast.Name) and d.id == "entrypoint" for d in fn.decorator_list)}
    calls: dict[str, set[str]] = {}
    dynamic: set[str] = set()
    for name, fn in functions.items():
        calls[name] = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls[name].add(node.func.id)
                else:
                    dynamic.add(name)
    edges = 0

    def predecessors(seeds: set[str]) -> set[str]:
        nonlocal edges
        # Reverse reachability handles recursion using a visited set.
        reverse: dict[str, set[str]] = {}
        for caller, targets in calls.items():
            for target in targets:
                edges += 1
                reverse.setdefault(target, set()).add(caller)
        found = set(seeds)
        pending = list(sorted(seeds))
        while pending:
            node = pending.pop()
            for caller in sorted(reverse.get(node, ())):
                edges += 1
                if caller not in found:
                    found.add(caller)
                    pending.append(caller)
        return found

    lexical = {n for n in functions if any(k in n.lower() for k in KEYWORDS)}
    named = entries & lexical
    reasons: dict[str, list[str]] = {}
    if strategy == "name":
        candidates = named
    elif strategy == "name_callers":
        candidates = entries & predecessors(lexical)
    elif strategy == "effect":
        candidates = entries & predecessors(set(sinks))
    elif strategy == "union":
        candidates = entries & (predecessors(set(sinks)) | predecessors(lexical))
    else:
        candidates = entries
    for name in sorted(candidates):
        reasons[name] = ["selected_by:" + strategy]
    # Compute unresolved calls separately, for all methods. These do not count
    # as successful discovery. They can prevent a claim of inventory closure.
    unresolved_functions = set(dynamic)
    for caller, targets in calls.items():
        if any(t not in functions and t not in sinks and t not in SAFE_EXTERNAL for t in targets):
            unresolved_functions.add(caller)
    # Count this pass as well: identical uncertainty handling is shared.
    unresolved = entries & predecessors(unresolved_functions)
    for name in sorted(unresolved):
        reasons.setdefault(name, []).append("unresolved_or_dynamic_call")
    return Discovery(strategy, tuple(sorted(entries)), tuple(sorted(candidates)),
                     tuple(sorted(unresolved)), reasons, len(source.encode()),
                     sum(1 for _ in ast.walk(tree)), edges)


def probe(source: str) -> dict:
    """Run trusted fixture code under fixed inputs to label observed outputs.

    This is NOT a sandbox, and labels only the stated finite input set. The
    scanner does not call this function or receive its results.
    """
    entries: dict[str, object] = {}
    events: list[dict] = []
    def entrypoint(fn):
        entries[fn.__name__] = fn
        return fn
    def sink(row):
        events.append(dict(row))
    def permitted(actor, row):
        return actor["role"] == "manager" and actor["tenant"] == row["tenant"]
    namespace = {"entrypoint": entrypoint, "emit_document": sink,
                 "archive_document": sink, "permitted": permitted}
    exec(compile(source, "trusted_route_fixture", "exec"), namespace)
    samples = [({"role": "manager", "tenant": "tenant-a"}, "tenant-a", True),
               ({"role": "manager", "tenant": "tenant-a"}, "tenant-b", False),
               ({"role": "viewer", "tenant": "tenant-a"}, "tenant-a", False)]
    positive, faults, details = [], [], {}
    for name, fn in sorted(entries.items()):
        observed = False
        violations = []
        for actor, tenant, allowed in samples:
            row = {"tenant": tenant, "document_id": "sensitive-document", "title": "sample"}
            events.clear()
            fn(actor, row)
            emitted = any(e.get("document_id") == "sensitive-document" for e in events)
            observed = observed or emitted
            if emitted and not allowed:
                violations.append({"actor": actor, "row_tenant": tenant})
        if observed:
            positive.append(name)
        if violations:
            faults.append(name)
        details[name] = {"emits_declared_document": observed, "violations": violations}
    return {"entries": sorted(entries), "positive": positive, "faults": faults,
            "input_cases_per_entry": len(samples), "details": details}


def compare(source: str, strategy: str, gold: dict | None = None) -> dict:
    found = scan(source, strategy)
    truth = gold if gold is not None else probe(source)
    selected, relevant = set(found.candidates), set(truth["positive"])
    universe = set(truth["entries"])
    return {"strategy": strategy, "tp": len(selected & relevant),
            "fp": len(selected - relevant), "fn": len(relevant - selected),
            "tn": len(universe - (selected | relevant)),
            "candidate_count": len(selected), "unresolved_count": len(found.unresolved),
            "unresolved_entries": list(found.unresolved),
            "selected": list(found.candidates), "missed": sorted(relevant - selected),
            "unnecessary": sorted(selected - relevant),
            "source_bytes": found.source_bytes, "ast_nodes": found.ast_nodes,
            "edges_examined": found.edges_examined}
