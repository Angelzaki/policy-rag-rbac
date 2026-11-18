from __future__ import annotations

import re
import unicodedata

# Intentos de saltarse el rol asignado / ACL (problema central).
ESCALATION_PATTERNS = [
    r"ignora\s+(el\s+)?(rol|acl|permiso|restriccion)",
    r"ignore\s+(the\s+)?(role|acl|permission)",
    r"actua\s+como\s+(auditor|admin|administrador|root)",
    r"act\s+as\s+(auditor|admin|administrator|root)",
    r"eres\s+(ahora\s+)?(auditor|admin)",
    r"cambia\s+(mi\s+)?rol\s+a",
    r"eleva\s+(mis\s+)?privilegios",
    r"break[\s-]?glass\s+sin\s+aprob",
    r"muestra\s+(todos|todas)\s+los\s+(documentos|politicas)",
    r"sin\s+filtro\s+(de\s+)?(rol|rbac|acl)",
    r"override\s+(acl|rbac|role)",
    r"jailbreak",
    r"dan\s+mode",
    r"system\s*:\s*you\s+are",
    r"revela\s+(el\s+)?prompt\s+del\s+sistema",
]


def _fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in nfkd if not unicodedata.combining(c))
    return plain.lower()


def screen(question: str, role: str) -> dict | None:
    """Bloquea intentos de escalada de privilegio / bypass de ACL."""
    folded = _fold(question)
    matched = []
    for pat in ESCALATION_PATTERNS:
        if re.search(pat, folded):
            matched.append(pat)
    if not matched:
        return None
    return {
        "answer": (
            "Consulta bloqueada: intento de escalada de privilegio o bypass de ACL. "
            "El rol efectivo no se puede cambiar desde el prompt."
        ),
        "citations": [],
        "score": 0.0,
        "overlap": 0.0,
        "role": role,
        "status": "blocked",
        "abstained": True,
        "rbac_ok": True,
        "blocked": True,
        "reason": "privilege_escalation",
        "matched_patterns": matched[:3],
        "question": question,
        "denied_near_miss": None,
        "leak_pressure": False,
    }
