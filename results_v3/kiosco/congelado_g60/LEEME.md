# Banco de kiosco congelado de G-60

Redactado el 2026-09-26 **después** de `freeze-G-60` (motor `bfb9aaef`).
- Lo escribieron 6 redactores nuevos (herramienta Agent con `isolation: "worktree"`, nunca *fork*), sin el preregistro, sin mensajes del usuario y sin ejemplos.
- El encargo fue el neutral: `../encargo_redactor.md`.
- Modelos: Y1 y Y6 Opus, Y2 y Y5 Sonnet 5, Y3 Haiku 4.5, Y4 Fable 5.1.
- 24 sectores distintos de los 96 negocios anteriores.
- Es texto de modelos de lenguaje, declarado; nunca entra al motor.

La validación automática está en `validacion_automatica.json` (el banco no se leyó). Da 639 turnos, y 19 de las 518 claves no aparecen literalmente en el texto.

Y3 escribió cada archivo como una lista plana de turnos. El evaluador la lee como una sola conversación, en su orden: es un cambio de forma, sin tocar el contenido.
