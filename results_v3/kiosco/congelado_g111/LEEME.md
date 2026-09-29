# Banco de kiosco congelado de G-111b (32 negocios)

Redactado el 2026-09-29 **después** de congelar el motor (`freeze-G111-1`, commit `62a688a`, huella `d1c92eb74b5d58420fc698aec30ea334bd1ad27d`)
y antes de ejecutar Leobot sobre él.
- 8 redactores nuevos (Agent con `isolation: "worktree"`, nunca *fork*), sin el preregistro, sin mensajes del usuario y sin ejemplos; leyeron
  solo `results_v3/kiosco/encargo_redactor_g111.md` con `git show 62a688a:…`. Modelos: W1 y W5 Opus, W2 y W6 Sonnet 5, W3 y W7 Haiku 4.5,
  W4 y W8 Fable 5.1. 4 negocios cada uno; 826 turnos: directa 238, si_no 134, combinada 62, seguimiento 105, instruccion 87,
  sin_respuesta 162, charla 38.
- Texto de modelos de lenguaje, declarado; nunca entra al motor.
- **Sectores repetidos (declarado antes de ejecutar):** `W3/n1` (ecolodge: hotel), `W3/n2` (fisioterapia), `W3/n3` (tours), `W3/n4` (muebles),
  `W7/n1` (odontología), `W7/n4` (tienda de ropa). Se informa también el resultado sin esos seis (26 negocios). Dentro del banco se repiten
  sector: trofeos (`W1/n1`, `W5/n3`), fabricación digital (`W1/n2`, `W5/n4`), agroservicio (`W5/n2`, `W6/n3`), concesionaria (`W4/n3`,
  `W6/n4`), aeroclub (`W2/n3`, `W4/n2`), colegio profesional (`W5/n1`, `W8/n4`).
- Las claves de las `combinada` pueden ser totales calculados (W2, W8 lo declaran).
