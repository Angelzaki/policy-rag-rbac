from __future__ import annotations

import argparse
import json
from pathlib import Path

import uvicorn

from policy_rag_rbac.experiment import evaluate, load_asks, to_markdown
from policy_rag_rbac.rag import PolicyRag

ROOT = Path(__file__).resolve().parents[2]


def _build_rag() -> PolicyRag:
    return PolicyRag(
        docs_dir=ROOT / "samples" / "policies",
        acl_path=ROOT / "samples" / "acl.json",
        roles_path=ROOT / "samples" / "roles.json",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="policy-rag-rbac")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ask = sub.add_parser("ask", help="Pregunta con rol")
    ask.add_argument("question")
    ask.add_argument("--role", required=True, help="analista_credito|soporte|rrhh|auditor|publico")

    roles = sub.add_parser("roles", help="Lista roles y docs autorizados")

    exp = sub.add_parser("experiment", help="Eval reproducible + gates")
    exp.add_argument("--file", default=str(ROOT / "samples" / "asks.jsonl"))
    exp.add_argument("--format", choices=["json", "md"], default="md")

    serve = sub.add_parser("serve", help="UI FastAPI")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8024)

    args = parser.parse_args(argv)
    rag = _build_rag()

    if args.cmd == "roles":
        out = {}
        for role in sorted(rag.roles):
            docs = [d["id"] for d in rag.docs_for_role(role)]
            out[role] = {"label": rag.roles[role].get("label"), "docs": docs}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "ask":
        print(json.dumps(rag.ask(args.question, args.role), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "experiment":
        report = evaluate(rag, load_asks(Path(args.file)))
        out_dir = ROOT / "results"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "experiment_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out_dir / "experiment_report.md").write_text(to_markdown(report) + "\n", encoding="utf-8")
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(to_markdown(report))
            print(
                f"\ngrounded {report['grounded_ok']}/{report['grounded_total']} · "
                f"abstain {report['abstain_ok']}/{report['abstain_total']} · "
                f"rbac {report['rbac_ok']}/{report['rbac_total']} · "
                f"total {report['passed']}/{report['total']}"
            )
            print(f"reportes → {out_dir}")
        return 0 if report["passed"] == report["total"] else 1

    if args.cmd == "serve":
        uvicorn.run("policy_rag_rbac.app:app", host=args.host, port=args.port)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
