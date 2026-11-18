# Conclusiones

1. **El problema no es solo “responder bien”**: es impedir que un rol vea un documento que el ranking habría preferido.
2. **Shadow rank** hace visible la presión de filtración: abstenerse con `denied_near_miss` demuestra el valor del RBAC.
3. **Doble puerta ACL ∩ clearance**: fraude/PLD/logs quedan en `confidencial`; el analista ve crédito pero no fraude.
4. **La escalada por prompt debe bloquearse antes del retrieval**; el rol efectivo no se negocia en lenguaje natural.
5. **Break-glass no es un atajo**: sin aprobación humana no eleva; queda auditado como solicitud.
6. **Gates CI de `suite.rbac` + `suite.blocked` + `suite.pressure`** evitan regresiones de seguridad silenciosas.
