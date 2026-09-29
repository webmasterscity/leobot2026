# Banco congelado de G-115 (32 negocios, 842 turnos)

Redactado el 2026-09-29 **después** de congelar y antes de ejecutar Leobot.
- Congelado: `freeze-G115-1` = commit `de14e50`, huella del motor `d1c92eb74b5d58420fc698aec30ea334bd1ad27d`. La base elegida, `g115_reemplazo.json`, tiene sha256 `ed71f561…`.
- 8 redactores nuevos (Agent con `isolation: "worktree"`, nunca *fork*):
  - W1 y W5: Opus;
  - W2 y W6: Sonnet;
  - W3 y W7: Haiku;
  - W4 y W8: Fable.
- No recibieron el preregistro, mensajes del usuario ni ejemplos. Solo leyeron `git show e404cdf:results_v3/kiosco/encargo_redactor_g115.md`.
- Es texto de modelos de lenguaje, declarado como tal; nunca entra al motor.

**Declarado antes de ejecutar:**
- Sectores repetidos o cercanos a los excluidos:
  - `W7/n3` «Aventura Andina Tours», casi el mismo nombre que un excluido;
  - `W3/n1` y `W3/n3` (hotel y hospedaje), porque ya había hoteles;
  - `W7/n4` (libros y café ~ librería y café);
  - `W4/n2` (cementerio ~ funeraria);
  - `W7/n2` (motos).
- Repetidos dentro del banco:
  - esgrima (`W4/n3`, `W8/n3`);
  - cerería (`W1/n2`, `W8/n4`).
- W3 (73 turnos) y W7 (85) escribieron menos de lo pedido.
- 5 turnos `sin_respuesta` con acción `responder`. Quedan fuera del criterio 3, como en G-114b.
- Se usa el banco completo, como en G-114b. Si hace falta, se informará aparte, de forma descriptiva, el resultado sin los negocios declarados.

Tipos de turno:
- directa: 253;
- sí/no: 139;
- seguimiento: 103;
- combinada: 53;
- instrucción: 84;
- sin respuesta: 170, de ellos 165 coherentes;
- charla: 40.
