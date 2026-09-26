# Banco de kiosco congelado de G-63 (24 negocios, completado en dos tandas)

Redactado el 2026-09-26 **después** de `freeze-G-63` (motor `f348a8cf`).
- Lo escribieron redactores nuevos (herramienta Agent con `isolation: "worktree"`, nunca *fork*), sin el preregistro, sin mensajes del usuario y sin ejemplos.
- El encargo fue el neutral: `../encargo_redactor.md`.
- Sectores distintos de los 168 negocios anteriores.
- Es texto de modelos de lenguaje, declarado; nunca entra al motor.

**Primera tanda, cortada por el límite semanal de la API** (se reinicia el 30 de septiembre):
- R2 (Sonnet 5) y R3 (Haiku 4.5) terminaron sus 4 negocios.
- R1 (Opus) se cortó al final: sus 4 negocios están completos (tres archivos, JSON válido, 29 turnos cada uno).
- R6 (Opus) se cortó con 3 negocios completos; el cuarto quedó a medias y no se incluye.
- R4 (Fable 5.1) y R5 (Sonnet 5) no alcanzaron a escribir.

**Segunda tanda (2026-09-26, más tarde, mismo motor congelado `f348a8cf`):** tres redactores nuevos, con el mismo encargo neutral y los mismos sectores previstos, escribieron los 9 que faltaban. Las cifras de la primera tanda ya se habían visto, pero los redactores no las conocen.
- R4: 4 negocios, escritos por Sonnet 5 en lugar de Fable 5.1 (desvío declarado: el banco queda con 3 modelos, no 4).
- R5: 4 negocios, Sonnet 5, como estaba previsto.
- R6 n4: 1 negocio, Opus, como estaba previsto; reemplaza al cuarto que quedó a medias.

Total: 24 negocios y 619 turnos.

Validación automática en `validacion_automatica.json` (el banco no se leyó).
