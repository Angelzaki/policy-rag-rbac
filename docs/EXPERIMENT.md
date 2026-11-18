# Experimento

## Base (`asks.jsonl` · 21 casos)

```bash
python -m policy_rag_rbac experiment
```

| Suite | Qué mide |
|-------|----------|
| grounded | Respuesta correcta en alcance |
| abstain | Abstención cuando el rol no tiene el doc |
| rbac | Cero citas a `forbidden_docs` |
| pressure | `leak_pressure` cuando el shadow near-miss existe |

## Adversarial (`asks_adversarial.jsonl` · 18 casos)

```bash
python -m policy_rag_rbac experiment --adversarial
```

| Suite | Qué mide |
|-------|----------|
| blocked | Escalada / jailbreak / override ACL |
| pressure + near-miss | Doc denegado que habría ganado sin RBAC |
| grounded control | Auditor/analista siguen resolviendo en alcance |

## Gates CI

- `ci/thresholds.yaml` → base
- `ci/thresholds_adversarial.yaml` → adversarial (`suite.blocked`, `suite.pressure`)
