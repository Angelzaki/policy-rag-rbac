from __future__ import annotations

from pathlib import Path

import pytest

from policy_rag_rbac.rag import PolicyRag

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def rag() -> PolicyRag:
    return PolicyRag(
        docs_dir=ROOT / "samples" / "policies",
        acl_path=ROOT / "samples" / "acl.json",
        roles_path=ROOT / "samples" / "roles.json",
        classifications_path=ROOT / "samples" / "classifications.json",
    )
