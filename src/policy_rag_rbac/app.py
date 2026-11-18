from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from policy_rag_rbac.audit import AuditLog
from policy_rag_rbac.metrics import compute_stats
from policy_rag_rbac.rag import PolicyRag

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("POLICY_RAG_DATA", str(ROOT / "data")))
RAG = PolicyRag(
    docs_dir=ROOT / "samples" / "policies",
    acl_path=ROOT / "samples" / "acl.json",
    roles_path=ROOT / "samples" / "roles.json",
    classifications_path=ROOT / "samples" / "classifications.json",
)
AUDIT = AuditLog(DATA_DIR / "audit.json")
TEMPLATES = Jinja2Templates(directory=str(ROOT / "templates"))

app = FastAPI(title="policy-rag-rbac")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def _context(request: Request, result: dict | None, question: str = "", role: str = "soporte") -> dict:
    rows = AUDIT.all()
    return {
        "request": request,
        "result": result,
        "question": question,
        "role": role,
        "roles": RAG.roles,
        "history": list(reversed(rows))[:20],
        "stats": compute_stats(rows),
        "doc_count": len(RAG.docs),
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return TEMPLATES.TemplateResponse(request, "index.html", _context(request, None))


@app.post("/ask", response_class=HTMLResponse)
def ask(
    request: Request,
    question: str = Form(...),
    role: str = Form("soporte"),
    break_glass: str = Form(""),
    reason: str = Form(""),
):
    try:
        result = RAG.ask(
            question,
            role,
            break_glass=break_glass in {"1", "on", "true", "yes"},
            break_glass_reason=reason,
        )
    except ValueError as exc:
        result = {
            "answer": str(exc),
            "citations": [],
            "status": "error",
            "abstained": True,
            "rbac_ok": False,
            "role": role,
            "score": 0.0,
        }
    AUDIT.add({"question": question, **result})
    return TEMPLATES.TemplateResponse(
        request, "index.html", _context(request, result, question, role)
    )


@app.post("/clear")
def clear():
    AUDIT.path.write_text("[]", encoding="utf-8")
    return RedirectResponse("/", status_code=303)


@app.get("/api/ask")
def api_ask(q: str, role: str = "soporte", break_glass: bool = False, reason: str = ""):
    try:
        result = RAG.ask(q, role, break_glass=break_glass, break_glass_reason=reason)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    AUDIT.add({"question": q, **result})
    return JSONResponse(result)


@app.get("/api/roles")
def api_roles():
    out = {}
    for role in sorted(RAG.roles):
        out[role] = {
            "label": RAG.roles[role].get("label"),
            "clearance": RAG.roles[role].get("clearance"),
            "docs": [d["id"] for d in RAG.docs_for_role(role)],
        }
    return JSONResponse(out)


@app.get("/api/stats")
def api_stats():
    return JSONResponse(compute_stats(AUDIT.all()))


@app.get("/health")
def health():
    return {
        "status": "ok",
        "docs": len(RAG.docs),
        "roles": sorted(RAG.roles),
        "layers": ["acl", "clearance", "guard", "shadow_rank"],
    }
