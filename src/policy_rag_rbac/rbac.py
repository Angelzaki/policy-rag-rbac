from __future__ import annotations

import json
from pathlib import Path


def load_roles(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data.get("roles") or {})


def load_acl(path: Path) -> dict[str, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): list(v) for k, v in data.items()}


def load_classifications(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): dict(v) for k, v in data.items()}


def assert_role(roles: dict[str, dict], role: str) -> str:
    if role not in roles:
        known = ", ".join(sorted(roles))
        raise ValueError(f"rol desconocido: {role}. Roles válidos: {known}")
    return role


def role_clearance(roles: dict[str, dict], role: str) -> int:
    meta = roles.get(role) or {}
    return int(meta.get("clearance", 0))


def doc_level(classifications: dict[str, dict], doc_id: str) -> int:
    meta = classifications.get(doc_id) or {}
    return int(meta.get("level", 0))


def allowed_doc_ids(
    acl: dict[str, list[str]],
    role: str,
    roles: dict[str, dict] | None = None,
    classifications: dict[str, dict] | None = None,
) -> set[str]:
    """ACL por rol ∩ clearance ≥ clasificación del documento (ABAC lite)."""
    clearance = role_clearance(roles or {}, role) if roles else 99
    out: set[str] = set()
    for doc_id, role_list in acl.items():
        if role not in role_list:
            continue
        if classifications is not None and doc_level(classifications, doc_id) > clearance:
            continue
        out.add(doc_id)
    return out
