# Experimento

## Cómo correr

```bash
pip install -e ".[dev]"
python -m policy_rag_rbac experiment
pytest -q
```

Salida: `results/experiment_report.json` y `.md`.

## Suites (20 casos)

| Suite | Casos | Qué mide |
|-------|-------|----------|
| grounded | g01–g10 | Respuesta correcta **con** evidencia en alcance del rol |
| abstain | a01–a08 | Abstención cuando el rol no tiene el doc |
| leak / rbac | l01–l02 + forbidden_docs en todos | Cero citas a docs prohibidos |

## Gate CI

Umbrales en `ci/thresholds.yaml`:

- `overall: 1.0`
- `suite.grounded: 1.0`
- `suite.abstain: 1.0`
- `suite.rbac: 1.0`

## Datos

Corpus 100% sintético (`samples/policies`). Sin documentos reales de ningún banco.
