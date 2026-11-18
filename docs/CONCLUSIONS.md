# Conclusiones

1. **RBAC en retrieval es el diferencial.** Un copiloto grounded sin ACL sigue siendo un riesgo de filtración en entornos regulados.
2. **Abstenerse es correcto.** Soporte preguntando por límites de crédito o umbrales PLD debe recibir abstención, no una paráfrasis “útil”.
3. **Eval de filtración es tan importante como recall.** `suite.rbac` debe ser gate de CI, no un KPI cosmético.
4. **Pre-filter > post-filter.** Si el documento no autorizado entra al ranking, el sistema ya falló el modelo mental de seguridad.
5. **Siguiente profundidad:** freshness por versión de política, ACL por atributo (ABAC), y traces por consulta en el mismo audit log.
