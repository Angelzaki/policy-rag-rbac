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

    # Defensa: ningún citation fuera de allowed_docs del resultado.
    allowed = set(result.get("allowed_docs") or [])
    if citations and allowed:
        outside = [c for c in citations if c not in allowed]
        if outside:
            return False, f"cita fuera de ACL: {outside}"

    return True, "ok"


def evaluate(rag: PolicyRag, cases: list[dict]) -> dict:
    details = []
    passed = 0
    grounded_ok = grounded_total = 0
    abstain_ok = abstain_total = 0
    rbac_ok = rbac_total = 0

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

        rbac_total += 1
        citations = list(result.get("citations") or [])
        forbidden = set(case.get("forbidden_docs") or [])
        leak = any(c in forbidden for c in citations)
        if not leak and result.get("rbac_ok", True):
            rbac_ok += 1

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
            }
        )

    total = len(cases) or 1
    overall = passed / total
    suite_grounded = (grounded_ok / grounded_total) if grounded_total else 1.0
    suite_abstain = (abstain_ok / abstain_total) if abstain_total else 1.0
    suite_rbac = (rbac_ok / rbac_total) if rbac_total else 1.0

    return {
        "passed": passed,
        "total": len(cases),
        "overall": overall,
        "grounded_ok": grounded_ok,
        "grounded_total": grounded_total,
        "abstain_ok": abstain_ok,
        "abstain_total": abstain_total,
        "rbac_ok": rbac_ok,
        "rbac_total": rbac_total,
        "suite.grounded": suite_grounded,
        "suite.abstain": suite_abstain,
        "suite.rbac": suite_rbac,
        "details": details,
    }


def to_markdown(report: dict) -> str:
    lines = [
        "# policy-rag-rbac · experimento",
        "",
        f"- overall: **{report['passed']}/{report['total']}** ({report['overall']:.0%})",
        f"- grounded: {report['grounded_ok']}/{report['grounded_total']}",
        f"- abstain: {report['abstain_ok']}/{report['abstain_total']}",
        f"- rbac (sin filtración): {report['rbac_ok']}/{report['rbac_total']}",
        "",
        "| id | rol | expect | ok | status | citas |",
        "|----|-----|--------|----|--------|-------|",
    ]
    for d in report["details"]:
        cites = ", ".join(d.get("citations") or []) or "—"
        mark = "✓" if d["ok"] else "✗"
        lines.append(
            f"| {d['id']} | {d['role']} | {d['expect']} | {mark} | {d['status']} | {cites} |"
        )
    fails = [d for d in report["details"] if not d["ok"]]
    if fails:
        lines += ["", "## Fallos", ""]
        for d in fails:
            lines.append(f"- `{d['id']}`: {d['reason']}")
    return "\n".join(lines)
