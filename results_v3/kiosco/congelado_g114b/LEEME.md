# Banco de kiosco congelado de G-114b (32 negocios, 842 turnos)

Redactado el 2026-09-29 **después** de congelar (`freeze-G114b-1` = commit `e719c48`, huella `d1c92eb74b5d58420fc698aec30ea334bd1ad27d`) y
antes de ejecutar Leobot. 8 redactores nuevos (Agent con `isolation: "worktree"`, nunca *fork*; W1 y W5 Opus, W2 y W6 Sonnet 5, W3 y W7 Haiku 4.5,
W4 y W8 Fable 5.1), sin el preregistro, sin mensajes del usuario, sin ejemplos; leyeron solo `git show e719c48:results_v3/kiosco/encargo_redactor_g114b.md`.
Texto de modelos de lenguaje, declarado; nunca entra al motor.
- **Declarado antes de ejecutar:** sectores repetidos `W3/n1` (farmacia), `W3/n3` (cine), `W3/n4` (librería), `W7/n4` (tienda de discos);
  cercanos `W7/n1` (tintorería ~ lavandería) y `W2/n1` (monitoreo de alarmas ~ cerrajería y seguridad). Repetidos dentro del banco: OMIC
  (`W5/n3`, `W8/n4`), drones (`W1/n3`, `W8/n2`). W3 escribió 51 turnos en total (menos de lo pedido). 1 turno `sin_respuesta` con acción
  distinta de abstenerse/derivar (queda fuera del criterio 3 por el preregistro).
