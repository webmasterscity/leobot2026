# Banco de kiosco congelado de G-112 (32 negocios)

Redactado el 2026-09-29 **después** de congelar (`freeze-G112-1` = commit `342dc4b`, huella del motor `d1c92eb74b5d58420fc698aec30ea334bd1ad27d`)
y antes de ejecutar Leobot sobre él. 8 redactores nuevos (Agent con `isolation: "worktree"`, nunca *fork*; W1 y W5 Opus, W2 y W6 Sonnet 5,
W3 y W7 Haiku 4.5, W4 y W8 Fable 5.1), sin el preregistro, sin mensajes del usuario, sin ejemplos; leyeron solo
`git show 342dc4b:results_v3/kiosco/encargo_redactor_g112.md`. Texto de modelos de lenguaje, declarado; nunca entra al motor.
- W7 declaró 101 turnos pero sus archivos tienen 77 (conversaciones como objetos `{"conversacion": [...]}`, que el lector ya admite).
- **Sectores repetidos (declarado antes de ejecutar):** `W3/n1` (restaurante), `W3/n2` (consultorio médico), `W3/n4` (hotel), `W7/n2`
  (escuela de idiomas), `W7/n3` (salón de belleza), `W7/n4` (medicina preventiva). Se informa también sin esos seis (26 negocios).
  Repetidos dentro del banco: toldos y persianas (`W1/n1`, `W5/n1`, `W4/n4`), hielo (`W1/n2`, `W5/n4`), numismática (`W1/n3`, `W4/n2`,
  `W8/n3`), artículos deportivos (`W3/n3`, `W7/n1`, `W8/n2`).
