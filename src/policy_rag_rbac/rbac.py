from __future__ import annotations

import json
from pathlib import Path


def load_roles(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data.get("roles") or {})


def load_acl(path: Path) -> dict[str, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): list(v) for k, v in data.items()}


def allowed_doc_ids(acl: dict[str, list[str]], role: str) -> set[str]:
    return {doc_id for doc_id, roles in acl.items() if role in roles}


def assert_role(roles: dict[str, dict], role: str) -> str:
    if role not in roles:
        known = ", ".join(sorted(roles))
        raise ValueError(f"rol desconocido: {role}. Roles válidos: {known}")
    return role
