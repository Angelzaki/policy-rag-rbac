from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from policy_rag_rbac.rbac import allowed_doc_ids, assert_role, load_acl, load_roles

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


def load_docs(docs_dir: Path, acl: dict[str, list[str]]) -> list[dict]:
    docs = []
    for path in sorted(docs_dir.glob("*.txt")):
        doc_id = path.stem
        docs.append(
            {
                "id": doc_id,
                "text": path.read_text(encoding="utf-8"),
                "roles": list(acl.get(doc_id, [])),
            }
        )
    return docs


class PolicyRag:
    """RAG léxico con filtro RBAC *antes* del retrieval."""

    def __init__(
        self,
        docs_dir: Path,
        acl_path: Path,
        roles_path: Path,
        min_score: float = 0.10,
        min_overlap: float = 0.30,
    ):
        self.roles = load_roles(roles_path)
        self.acl = load_acl(acl_path)
        self.docs = load_docs(docs_dir, self.acl)
        self.min_score = min_score
        self.min_overlap = min_overlap
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
        allowed = allowed_doc_ids(self.acl, role)
        return [d for d in self.docs if d["id"] in allowed]

    def ask(self, question: str, role: str) -> dict:
        role = assert_role(self.roles, role)
        allowed = allowed_doc_ids(self.acl, role)
        candidates = [(i, d) for i, d in enumerate(self.docs) if d["id"] in allowed]
        if not candidates:
            return self._abstain(question, role, "rol sin documentos autorizados", allowed)

        q_tokens = tokenize(question)
        tf = Counter(q_tokens)
        length = len(q_tokens) or 1
        q_vec = {t: (c / length) * self.idf.get(t, 0.0) for t, c in tf.items()}

        ranked: list[tuple[float, dict]] = []
        for i, doc in candidates:
            vec = self.vectors[i]
            keys = set(q_vec) | set(vec)
            if not keys:
                score = 0.0
            else:
                dot = sum(q_vec.get(x, 0.0) * vec.get(x, 0.0) for x in keys)
                na = math.sqrt(sum(v * v for v in q_vec.values()) or 1)
                nb = math.sqrt(sum(v * v for v in vec.values()) or 1)
                score = dot / (na * nb)
            ranked.append((score, doc))
        ranked.sort(key=lambda x: x[0], reverse=True)
        top_score, top = ranked[0]

        # Defensa en profundidad: nunca citar fuera de ACL.
        if top["id"] not in allowed:
            return self._abstain(question, role, "filtración RBAC", allowed)

        content = content_tokens(question)
        ctx = set(tokenize(top["text"]))
        core = [t for t in content if t not in SOFT_MISS]
        overlap = 0.0
        if core:
            overlap = sum(1 for t in core if t in ctx) / len(core)
        elif content:
            overlap = sum(1 for t in content if t in ctx) / len(content)

        hard_miss = [t for t in content if t not in ctx and t not in SOFT_MISS and len(t) >= 5]
        # Temas ajenos al corpus autorizado → abstenerse (no inventar).
        if hard_miss and top_score < 0.22:
            return self._abstain(
                question,
                role,
                "sin evidencia autorizada suficiente",
                allowed,
                score=top_score,
                overlap=overlap,
            )
        if top_score < self.min_score or overlap < self.min_overlap:
            return self._abstain(
                question,
                role,
                "sin evidencia autorizada suficiente",
                allowed,
                score=top_score,
                overlap=overlap,
            )

        answer = self._pick_sentence(top["text"], content)
        citations = [top["id"]]
        leaked = [c for c in citations if c not in allowed]
        if leaked:
            return self._abstain(question, role, "filtración RBAC bloqueada", allowed)

        return {
            "answer": answer,
            "citations": citations,
            "score": round(top_score, 4),
            "overlap": round(overlap, 4),
            "role": role,
            "allowed_docs": sorted(allowed),
            "status": "answered",
            "abstained": False,
            "rbac_ok": True,
        }

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
        score: float = 0.0,
        overlap: float = 0.0,
    ) -> dict:
        return {
            "answer": (
                "No tengo evidencia autorizada para tu rol. "
                "No puedo citar políticas fuera de tu alcance. Abstención."
            ),
            "citations": [],
            "score": round(score, 4),
            "overlap": round(overlap, 4),
            "role": role,
            "allowed_docs": sorted(allowed),
            "status": "abstained",
            "abstained": True,
            "rbac_ok": True,
            "reason": reason,
            "question": question,
        }
