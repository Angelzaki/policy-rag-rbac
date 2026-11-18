# Arquitectura · policy-rag-rbac

## Problema

En un asistente interno sobre políticas, el riesgo no es solo alucinar: es **filtrar** un documento que el rol del usuario no debería ver. Un RAG sin ACL responde “bien” y rompe confidencialidad.

## Diseño

```mermaid
flowchart TD
  U[Usuario + rol] --> A[API / CLI]
  A --> F[Filtro RBAC pre-retrieval]
  ACL[(acl.json)] --> F
  CORPUS[(policies/*.txt)] --> F
  F --> R[Índice léxico TF-IDF solo docs autorizados]
  R -->|score/overlap OK| ANS[Respuesta + citas ⊆ ACL]
  R -->|sin evidencia| ABS[Abstención + audit]
  ANS --> LOG[(audit.json)]
  ABS --> LOG
```

## Piezas

| Módulo | Responsabilidad |
|--------|-----------------|
| `rbac.py` | Roles, ACL, docs permitidos por rol |
| `rag.py` | Retrieval **después** del filtro; defensa en profundidad en citas |
| `experiment.py` | Suites grounded / abstain / rbac (anti-filtración) |
| `app.py` | UI + `/api/ask?role=` + auditoría |
| `llm-ci-gates` | Barrera CI sobre `suite.rbac` |

## Invariante de seguridad

> Toda cita devuelta pertenece al conjunto `allowed_docs(role)`.  
> Preguntas fuera de alcance → `status=abstained`, `citations=[]`.

El filtro es **pre-retrieval** (no post-hoc): los documentos no autorizados ni siquiera entran al ranking.
