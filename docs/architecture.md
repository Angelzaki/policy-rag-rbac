# Arquitectura · policy-rag-rbac

## Problema

Un asistente de políticas “grounded” **sin control de acceso** filtra crédito, fraude o PLD a roles que no deberían verlos. El fallo típico es post-filtrar citas: el documento ya entró al contexto.

## Capas de defensa

```mermaid
flowchart TD
  U[Usuario + rol + clearance] --> G[1 Guard anti-escalada]
  G -->|blocked| AUD[(audit.json)]
  G --> ACL[2 ACL por rol]
  ACL --> CL[3 Clearance ≥ clasificación]
  CL --> R[4 Retrieval solo en alcance]
  R --> SH[5 Shadow rank sobre docs denegados]
  R -->|evidencia OK| ANS[Respuesta + citas ⊆ ACL]
  R -->|sin evidencia| ABS[Abstención]
  SH -->|near-miss fuerte| LP[leak_pressure=true]
  ANS --> AUD
  ABS --> AUD
  LP --> AUD
```

| Capa | Qué evita |
|------|-----------|
| Guard | “Ignora el rol”, “actúa como auditor”, override ACL |
| ACL | Allow-list por documento |
| Clearance | Docs `confidencial` (3) exigen clearance ≥ 3 |
| Pre-retrieval | Docs fuera de alcance **no entran** al ranking autorizado |
| Shadow rank | Prueba que sin RBAC habría filtrado (near-miss) |
| Break-glass | No auto-eleva; roles no-auditor quedan `blocked` + audit |

## Invariante

> Toda cita ∈ `allowed_docs(role) = ACL(role) ∩ {docs \| level ≤ clearance(role)}`.  
> Intentos de escalada → `blocked`. Preguntas fuera de alcance → `abstained` + `denied_near_miss` si aplica.
