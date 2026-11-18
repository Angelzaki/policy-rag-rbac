from __future__ import annotations

import json
from pathlib import Path

from policy_rag_rbac.rag import PolicyRag


def load_asks(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _case_ok(case: dict, result: dict) -> tuple[bool, str]:
    expect = case.get("expect")
    status = result.get("status")
    if expect == "answered" and status != "answered":
        return False, f"esperado answered, got {status}"
    if expect == "abstained" and status != "abstained":
        return False, f"esperado abstained, got {status}"
    if expect == "blocked" and status != "blocked":
        return False, f"esperado blocked, got {status}"

    citations = list(result.get("citations") or [])
    forbidden = set(case.get("forbidden_docs") or [])
    leaked = [c for c in citations if c in forbidden]
    if leaked:
        return False, f"filtración RBAC: {leaked}"

    must = set(case.get("must_cite_any") or [])
    if must and expect == "answered":
        if not any(c in must for c in citations):
            return False, f"citas {citations} no incluyen {sorted(must)}"

    if not result.get("rbac_ok", True):
        return False, "rbac_ok=false"

    allowed = set(result.get("allowed_docs") or [])
    if citations and allowed:
        outside = [c for c in citations if c not in allowed]
        if outside:
            return False, f"cita fuera de ACL: {outside}"

    if case.get("expect_leak_pressure") and not result.get("leak_pressure"):
        return False, "se esperaba leak_pressure=true (shadow near-miss)"

    near_need = set(case.get("expect_near_miss_any") or [])
    if near_need:
        near = result.get("denied_near_miss") or {}
        if near.get("doc_id") not in near_need:
            return False, f"near_miss {near.get('doc_id')} no en {sorted(near_need)}"

    return True, "ok"


def evaluate(rag: PolicyRag, cases: list[dict]) -> dict:
    details = []
    passed = 0
    grounded_ok = grounded_total = 0
    abstain_ok = abstain_total = 0
    blocked_ok = blocked_total = 0
    rbac_ok = rbac_total = 0
    pressure_ok = pressure_total = 0

    for case in cases:
        result = rag.ask(case["question"], case["role"])
        ok, reason = _case_ok(case, result)
        if ok:
            passed += 1

        if case.get("expect") == "answered":
            grounded_total += 1
            if ok:
                grounded_ok += 1
        if case.get("expect") == "abstained":
            abstain_total += 1
            if ok:
                abstain_ok += 1
        if case.get("expect") == "blocked":
            blocked_total += 1
            if ok:
                blocked_ok += 1

        rbac_total += 1
        citations = list(result.get("citations") or [])
        forbidden = set(case.get("forbidden_docs") or [])
        leak = any(c in forbidden for c in citations)
        if not leak and result.get("rbac_ok", True):
            rbac_ok += 1

        if case.get("expect_leak_pressure"):
            pressure_total += 1
            if result.get("leak_pressure") and not leak:
                pressure_ok += 1

        details.append(
            {
                "id": case.get("id"),
                "role": case.get("role"),
                "expect": case.get("expect"),
                "ok": ok,
                "reason": reason,
                "status": result.get("status"),
                "citations": citations,
                "score": result.get("score"),
                "leak_pressure": result.get("leak_pressure"),
                "denied_near_miss": (result.get("denied_near_miss") or {}).get("doc_id"),
            }
        )

    total = len(cases) or 1
    overall = passed / total
    suite_grounded = (grounded_ok / grounded_total) if grounded_total else 1.0
    suite_abstain = (abstain_ok / abstain_total) if abstain_total else 1.0
    suite_blocked = (blocked_ok / blocked_total) if blocked_total else 1.0
    suite_rbac = (rbac_ok / rbac_total) if rbac_total else 1.0
    suite_pressure = (pressure_ok / pressure_total) if pressure_total else 1.0

    return {
        "passed": passed,
        "total": len(cases),
        "overall": overall,
        "grounded_ok": grounded_ok,
        "grounded_total": grounded_total,
        "abstain_ok": abstain_ok,
        "abstain_total": abstain_total,
        "blocked_ok": blocked_ok,
        "blocked_total": blocked_total,
        "rbac_ok": rbac_ok,
        "rbac_total": rbac_total,
        "pressure_ok": pressure_ok,
        "pressure_total": pressure_total,
        "suite.grounded": suite_grounded,
        "suite.abstain": suite_abstain,
        "suite.blocked": suite_blocked,
        "suite.rbac": suite_rbac,
        "suite.pressure": suite_pressure,
        "details": details,
    }


def to_markdown(report: dict) -> str:
    lines = [
        "# policy-rag-rbac · experimento",
        "",
        f"- overall: **{report['passed']}/{report['total']}** ({report['overall']:.0%})",
        f"- grounded: {report['grounded_ok']}/{report['grounded_total']}",
        f"- abstain: {report['abstain_ok']}/{report['abstain_total']}",
        f"- blocked (escalada): {report['blocked_ok']}/{report['blocked_total']}",
        f"- rbac (sin filtración): {report['rbac_ok']}/{report['rbac_total']}",
        f"- leak pressure detectada: {report['pressure_ok']}/{report['pressure_total']}",
        "",
        "| id | rol | expect | ok | status | citas | near-miss |",
        "|----|-----|--------|----|--------|-------|-----------|",
    ]
    for d in report["details"]:
        cites = ", ".join(d.get("citations") or []) or "—"
        mark = "✓" if d["ok"] else "✗"
        near = d.get("denied_near_miss") or "—"
        lines.append(
            f"| {d['id']} | {d['role']} | {d['expect']} | {mark} | {d['status']} | {cites} | {near} |"
        )
    fails = [d for d in report["details"] if not d["ok"]]
    if fails:
        lines += ["", "## Fallos", ""]
        for d in fails:
            lines.append(f"- `{d['id']}`: {d['reason']}")
    return "\n".join(lines)
