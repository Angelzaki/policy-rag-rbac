from __future__ import annotations

from collections import Counter


def compute_stats(rows: list[dict]) -> dict:
    total = len(rows)
    answered = sum(1 for r in rows if r.get("status") == "answered")
    abstained = sum(1 for r in rows if r.get("status") == "abstained")
    rbac_ok = sum(1 for r in rows if r.get("rbac_ok", True))
    scores = [float(r.get("score") or 0) for r in rows if r.get("status") == "answered"]
    avg_confidence = sum(scores) / len(scores) if scores else 0.0
    role_counts = Counter(str(r.get("role") or "?") for r in rows)
    cite_counts: Counter[str] = Counter()
    for r in rows:
        for c in r.get("citations") or []:
            cite_counts[str(c)] += 1
    return {
        "total": total,
        "answered": answered,
        "abstained": abstained,
        "abstain_rate": (abstained / total) if total else 0.0,
        "rbac_ok": rbac_ok,
        "rbac_rate": (rbac_ok / total) if total else 1.0,
        "avg_confidence": avg_confidence,
        "roles": role_counts.most_common(5),
        "top_sources": cite_counts.most_common(3),
    }
