from __future__ import annotations

from pathlib import Path

from policy_rag_rbac.experiment import evaluate, load_asks
from policy_rag_rbac.rag import PolicyRag

ROOT = Path(__file__).resolve().parents[1]


def test_roles_loaded(rag: PolicyRag):
    assert "soporte" in rag.roles
    assert "analista_credito" in rag.roles
    assert len(rag.docs) == 10


def test_soporte_no_ve_credito(rag: PolicyRag):
    ids = {d["id"] for d in rag.docs_for_role("soporte")}
    assert "sop-soporte-reset" in ids
    assert "pol-credito-limite" not in ids
    assert "pol-pld-kyc" not in ids


def test_analista_responde_limite(rag: PolicyRag):
    r = rag.ask("¿Cuál es el límite comercial estándar para persona natural?", "analista_credito")
    assert r["status"] == "answered"
    assert "pol-credito-limite" in r["citations"]
    assert r["rbac_ok"] is True


def test_soporte_abstiene_limite(rag: PolicyRag):
    r = rag.ask("¿Cuál es el límite comercial estándar para persona natural?", "soporte")
    assert r["status"] == "abstained"
    assert r["citations"] == []
    assert "pol-credito-limite" not in r["citations"]


def test_publico_no_ve_rrhh(rag: PolicyRag):
    r = rag.ask("¿Cuántos días de vacaciones tiene el personal?", "publico")
    assert r["status"] == "abstained"
    assert r["citations"] == []


def test_auditor_ve_pld(rag: PolicyRag):
    r = rag.ask("¿Qué documentos se requieren para completar KYC de un cliente nuevo?", "auditor")
    assert r["status"] == "answered"
    assert "pol-pld-kyc" in r["citations"]


def test_no_cita_fuera_de_acl(rag: PolicyRag):
    for role in rag.roles:
        allowed = {d["id"] for d in rag.docs_for_role(role)}
        r = rag.ask("política de límite comercial y score mínimo", role)
        for c in r.get("citations") or []:
            assert c in allowed, f"filtración: {role} citó {c}"


def test_experiment_full_pass(rag: PolicyRag):
    report = evaluate(rag, load_asks(ROOT / "samples" / "asks.jsonl"))
    fails = [d for d in report["details"] if not d["ok"]]
    assert report["passed"] == report["total"], fails
    assert report["suite.rbac"] == 1.0
