from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from policy_rag_rbac.guard import screen
from policy_rag_rbac.rbac import (
    allowed_doc_ids,
    assert_role,
    doc_level,
    load_acl,
    load_classifications,
    load_roles,
    role_clearance,
)

TOKEN = re.compile(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ0-9]+")
STOP = {
    "el",
    "la",
    "los",
    "las",
    "un",
    "una",
    "de",
    "del",
    "al",
    "en",
    "por",
    "con",
    "se",
    "si",
    "es",
    "no",
    "politica",
    "cual",
    "que",
    "como",
    "para",
    "sobre",
    "cuanto",
    "cuantos",
    "cuantas",
    "quien",
    "sintetica",
    "sintetico",
    "clasificacion",
    "interna",
}


def _fold(text: str) -> str:
    table = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    return text.translate(table).lower()


SYNONYMS = {
    "password": "contrasena",
    "clave": "contrasena",
    "claves": "contrasena",
    "restablecer": "reset",
    "restablecimiento": "reset",
    "tope": "limit",
    "maximo": "limit",
}

SOFT_MISS = {
    "soporte",
    "pedir",
    "nueva",
    "nuevo",
    "tiempo",
    "debe",
    "puedo",
    "puede",
    "pueden",
    "hasta",
    "tambien",
    "solo",
    "explicame",
    "dime",
    "cuales",
}


def stem(token: str) -> str:
    t = _fold(token)
    if t in SYNONYMS:
        t = SYNONYMS[t]
    if len(t) <= 3:
        return t
    if t.startswith("aprob") or t.startswith("aprue"):
        return "aprob"
    if t.startswith("excepc"):
        return "excepc"
    if t.startswith("limit"):
        return "limit"
    if t.startswith("score") or t.startswith("punt"):
        return "score"
    if t.startswith("desembol"):
        return "desembol"
    if t.startswith("fraud"):
        return "fraude"
    if t.startswith("alerta"):
        return "alerta"
    if t.startswith("reclamo"):
        return "reclamo"
    if t.startswith("vacacion"):
        return "vacacion"
    if t.startswith("acceso") or t.startswith("acces"):
        return "acceso"
    if t.startswith("contrasen") or t.startswith("password"):
        return "contrasena"
    if t.startswith("reset"):
        return "reset"
    if t.startswith("kyc") or t.startswith("conocim"):
        return "kyc"
    if t.startswith("lavado") or t.startswith("pld"):
        return "pld"
    if t.startswith("log"):
        return "log"
    if t.startswith("auditor"):
        return "auditor"
    if t.startswith("horario") or t.startswith("agencia"):
        return t[:6]
    if t.startswith("severidad") or t.startswith("sever"):
        return "severidad"
    for suf in ("mente", "ciones", "cion", "adores", "ador", "antes", "ante"):
        if t.endswith(suf) and len(t) - len(suf) >= 4:
            return t[: -len(suf)]
    if t.endswith("es") and len(t) > 5:
        return t[:-2]
    if t.endswith("s") and len(t) > 4 and not t.endswith("us"):
        return t[:-1]
    return t


def tokenize(text: str) -> list[str]:
    return [stem(t) for t in TOKEN.findall(text)]


def content_tokens(text: str) -> list[str]:
    out = []
    for raw in TOKEN.findall(text):
        folded = _fold(raw)
        keep_code = any(ch.isdigit() for ch in folded)
        if folded in STOP or (len(folded) <= 2 and not keep_code):
            continue
        s = stem(raw)
        if s in STOP or (len(s) <= 2 and not keep_code):
            continue
        out.append(s)
    return out


def load_docs(docs_dir: Path, acl: dict[str, list[str]], classifications: dict[str, dict]) -> list[dict]:
    docs = []
    for path in sorted(docs_dir.glob("*.txt")):
        doc_id = path.stem
        meta = classifications.get(doc_id) or {}
        docs.append(
            {
                "id": doc_id,
                "text": path.read_text(encoding="utf-8"),
                "roles": list(acl.get(doc_id, [])),
                "level": int(meta.get("level", 0)),
                "classification": str(meta.get("label", "publica")),
            }
        )
    return docs


class PolicyRag:
    """RAG léxico con filtro RBAC+clearance *antes* del retrieval y shadow rank anti-filtración."""

    def __init__(
        self,
        docs_dir: Path,
        acl_path: Path,
        roles_path: Path,
        classifications_path: Path | None = None,
        min_score: float = 0.10,
        min_overlap: float = 0.30,
        top_k: int = 2,
    ):
        self.roles = load_roles(roles_path)
        self.acl = load_acl(acl_path)
        class_path = classifications_path or (acl_path.parent / "classifications.json")
        self.classifications = load_classifications(class_path)
        self.docs = load_docs(docs_dir, self.acl, self.classifications)
        self.min_score = min_score
        self.min_overlap = min_overlap
        self.top_k = top_k
        self._tokenized = [tokenize(d["text"]) for d in self.docs]
        self._build_global_idf()

    def _build_global_idf(self) -> None:
        df: Counter[str] = Counter()
        for tokens in self._tokenized:
            df.update(set(tokens))
        n = len(self._tokenized) or 1
        self.idf = {t: math.log((n + 1) / (f + 1)) + 1.0 for t, f in df.items()}
        self.vectors = []
        for tokens in self._tokenized:
            tf = Counter(tokens)
            length = len(tokens) or 1
            self.vectors.append({t: (c / length) * self.idf[t] for t, c in tf.items()})

    def docs_for_role(self, role: str) -> list[dict]:
        assert_role(self.roles, role)
        allowed = allowed_doc_ids(self.acl, role, self.roles, self.classifications)
        return [d for d in self.docs if d["id"] in allowed]

    def _q_vec(self, question: str) -> dict[str, float]:
        q_tokens = tokenize(question)
        tf = Counter(q_tokens)
        length = len(q_tokens) or 1
        return {t: (c / length) * self.idf.get(t, 0.0) for t, c in tf.items()}

    def _score(self, q_vec: dict[str, float], doc_index: int) -> float:
        vec = self.vectors[doc_index]
        keys = set(q_vec) | set(vec)
        if not keys:
            return 0.0
        dot = sum(q_vec.get(x, 0.0) * vec.get(x, 0.0) for x in keys)
        na = math.sqrt(sum(v * v for v in q_vec.values()) or 1)
        nb = math.sqrt(sum(v * v for v in vec.values()) or 1)
        return dot / (na * nb)

    def _rank(self, q_vec: dict[str, float], indices: list[int]) -> list[tuple[float, dict]]:
        ranked = [(self._score(q_vec, i), self.docs[i]) for i in indices]
        ranked.sort(key=lambda x: x[0], reverse=True)
        return ranked

    def shadow_denied(self, question: str, allowed: set[str]) -> dict | None:
        """Mejor match en docs *no* autorizados. Mide presión de filtración si no hubiera RBAC."""
        q_vec = self._q_vec(question)
        denied_idx = [i for i, d in enumerate(self.docs) if d["id"] not in allowed]
        if not denied_idx:
            return None
        ranked = self._rank(q_vec, denied_idx)
        score, doc = ranked[0]
        if score < self.min_score:
            return None
        return {
            "doc_id": doc["id"],
            "score": round(score, 4),
            "classification": doc.get("classification"),
            "level": doc.get("level"),
        }

    def ask(self, question: str, role: str, break_glass: bool = False, break_glass_reason: str = "") -> dict:
        blocked = screen(question, role)
        if blocked:
            return blocked

        role = assert_role(self.roles, role)
        clearance = role_clearance(self.roles, role)

        # Break-glass no auto-eleva: exige humano (gobernanza). Solo auditor puede marcar auditoría elevada.
        if break_glass and role != "auditor":
            return {
                "answer": (
                    "Break-glass denegado para este rol. La elevación requiere aprobación humana "
                    "y solo queda registrada como solicitud."
                ),
                "citations": [],
                "score": 0.0,
                "overlap": 0.0,
                "role": role,
                "status": "blocked",
                "abstained": True,
                "rbac_ok": True,
                "blocked": True,
                "break_glass_requested": True,
                "break_glass_reason": break_glass_reason or "sin motivo",
                "reason": "break_glass_denied",
                "leak_pressure": False,
                "denied_near_miss": None,
            }

        allowed = allowed_doc_ids(self.acl, role, self.roles, self.classifications)
        near = self.shadow_denied(question, allowed)
        leak_pressure = bool(near and near["score"] >= 0.20)

        q_vec = self._q_vec(question)
        candidates = [i for i, d in enumerate(self.docs) if d["id"] in allowed]
        if not candidates:
            return self._abstain(
                question, role, "rol sin documentos autorizados", allowed, near, leak_pressure, clearance
            )

        ranked = self._rank(q_vec, candidates)
        top_score, top = ranked[0]

        if top["id"] not in allowed or doc_level(self.classifications, top["id"]) > clearance:
            return self._abstain(
                question, role, "filtración RBAC/clearance", allowed, near, leak_pressure, clearance
            )

        content = content_tokens(question)
        ctx = set(tokenize(top["text"]))
        core = [t for t in content if t not in SOFT_MISS]
        overlap = 0.0
        if core:
            overlap = sum(1 for t in core if t in ctx) / len(core)
        elif content:
            overlap = sum(1 for t in content if t in ctx) / len(content)

        hard_miss = [t for t in content if t not in ctx and t not in SOFT_MISS and len(t) >= 5]
        if hard_miss and top_score < 0.22:
            return self._abstain(
                question,
                role,
                "sin evidencia autorizada suficiente",
                allowed,
                near,
                leak_pressure,
                clearance,
                score=top_score,
                overlap=overlap,
            )
        if top_score < self.min_score or overlap < self.min_overlap:
            return self._abstain(
                question,
                role,
                "sin evidencia autorizada suficiente",
                allowed,
                near,
                leak_pressure,
                clearance,
                score=top_score,
                overlap=overlap,
            )

        citations = []
        for score, doc in ranked[: self.top_k]:
            if score < self.min_score:
                break
            # Evita segunda cita débil (ruido dentro del ACL).
            if citations and score < top_score * 0.72:
                break
            if doc["id"] not in allowed:
                continue
            if doc_level(self.classifications, doc["id"]) > clearance:
                continue
            citations.append(doc["id"])
        if not citations:
            return self._abstain(
                question, role, "filtración RBAC bloqueada", allowed, near, leak_pressure, clearance
            )

        answer = self._pick_sentence(top["text"], content)
        result = {
            "answer": answer,
            "citations": citations,
            "score": round(top_score, 4),
            "overlap": round(overlap, 4),
            "role": role,
            "clearance": clearance,
            "allowed_docs": sorted(allowed),
            "status": "answered",
            "abstained": False,
            "rbac_ok": True,
            "blocked": False,
            "leak_pressure": leak_pressure,
            "denied_near_miss": near,
        }
        if break_glass and role == "auditor":
            result["break_glass"] = True
            result["break_glass_reason"] = break_glass_reason or "auditoría elevada"
        return result

    def _pick_sentence(self, text: str, content: list[str]) -> str:
        sentences = []
        for s in re.split(r"[.\n]+", text):
            s = s.strip()
            if len(s) < 28:
                continue
            folded = _fold(s)
            if folded.startswith("pol-") or folded.startswith("sop-") or folded.startswith("faq-"):
                continue
            if folded.startswith("clasificacion"):
                continue
            sentences.append(s)
        if not sentences:
            sentences = [s.strip() for s in re.split(r"[.\n]+", text) if len(s.strip()) > 20]

        qset = set(content)
        sent_toks = [tokenize(s) for s in sentences]
        df_sent: Counter[str] = Counter()
        for toks in sent_toks:
            df_sent.update(set(toks) & qset)

        def sentence_score(stoks: list[str]) -> float:
            hits = [t for t in set(stoks) if t in qset]
            if not hits:
                return -1.0
            specificity = sum(1.0 / df_sent.get(t, 1) for t in hits)
            return len(hits) + 1.25 * specificity

        scored = [(sentence_score(toks), s) for s, toks in zip(sentences, sent_toks)]
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1] if scored else text[:200]
        return best if best.endswith(".") else best + "."

    def _abstain(
        self,
        question: str,
        role: str,
        reason: str,
        allowed: set[str],
        near: dict | None,
        leak_pressure: bool,
        clearance: int,
        score: float = 0.0,
        overlap: float = 0.0,
    ) -> dict:
        explain = reason
        if near and leak_pressure:
            explain = (
                f"{reason}. Sin RBAC el top match hubiera sido "
                f"`{near['doc_id']}` (score {near['score']}, {near.get('classification')}) — bloqueado."
            )
        return {
            "answer": (
                "No tengo evidencia autorizada para tu rol. "
                "No puedo citar políticas fuera de tu alcance. Abstención."
            ),
            "citations": [],
            "score": round(score, 4),
            "overlap": round(overlap, 4),
            "role": role,
            "clearance": clearance,
            "allowed_docs": sorted(allowed),
            "status": "abstained",
            "abstained": True,
            "rbac_ok": True,
            "blocked": False,
            "reason": explain,
            "question": question,
            "leak_pressure": leak_pressure,
            "denied_near_miss": near,
        }
