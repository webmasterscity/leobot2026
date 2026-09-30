# Banco congelado de G-115b (32 negocios, 802 turnos)

Redactado el 2026-09-29 **después** de congelar y antes de ejecutar Leobot.
- Congelado: `freeze-G115b-1` = commit `9e36272`, huella del motor `d1c92eb74b5d58420fc698aec30ea334bd1ad27d`.
- Base de G-115b: `g115b.json`, sha256 `9ab69ae5…`.
- 8 redactores nuevos (Agent con `isolation: "worktree"`, nunca *fork*):
  - W1 y W5: Opus;
  - W2 y W6: Sonnet;
  - W3 y W7: Haiku;
  - W4 y W8: Fable.
- No recibieron el preregistro, mensajes del usuario ni ejemplos. Solo leyeron `git show 9e36272:results_v3/kiosco/encargo_redactor_g115b.md`.
- Es texto de modelos de lenguaje, declarado como tal; nunca entra al motor.

**Declarado antes de ejecutar:**
- Sectores repetidos o cercanos a los excluidos:
  - `W4/n1` (escuela de fútbol infantil: hubo una en `congelado_g103`);
  - `W7/n3` (escuela de cocina: existía «Sazón del Norte»);
  - `W7/n4` (hotel ecológico: ya había hoteles);
  - `W3/n1` (luthería ~ instrumentos musicales);
  - `W4/n4` (alquiler para eventos ~ salón de eventos);
  - `W7/n2` (medicina deportiva ~ fisioterapia).
- Repetidos dentro del banco:
  - mediación vecinal (`W1/n2`, `W5/n1`);
  - migración (`W5/n4` albergue, `W8/n2` oficina);
  - enfermería (`W1/n3` cuidados, `W4/n3` instituto).
- W3 (69 turnos) y W7 (67) escribieron menos de lo pedido.
- 3 turnos `sin_respuesta` con acción `responder`. Quedan fuera del criterio 3.
- Se usa el banco completo, como en G-114b y G-115.
