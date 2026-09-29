# Banco de kiosco congelado de G-103/G-104/G-105 (31 negocios)

Redactado el 2026-09-28 **después** de `freeze-G103-1` (commit `fa15c4a`, motor `2d651fbd9a6f4e7a957dee77548ecb57e47abe30`) y antes de ejecutar
Leobot sobre él.
- Lo escribieron 8 redactores nuevos (herramienta Agent con `isolation: "worktree"`, nunca *fork*), sin el preregistro, sin mensajes del usuario y sin ejemplos.
  Modelos: W1 y W5 Opus, W2 y W6 Sonnet 5, W3 y W7 Haiku 4.5, W4 y W8 Fable 5.1. Se les indicó solo leer `../encargo_redactor_g103.md` (encargo neutral
  de siempre más la lista de nombres de los 216 negocios anteriores para evitar sectores repetidos, y «4 negocios por redactor»).
- Desvío declarado: W3 (Haiku) escribió 3 negocios en vez de 4 (31 en total). 838 turnos: directa 256, si_no 127, combinada 70, seguimiento 108,
  instruccion 88, sin_respuesta 155, charla 34.
- Es texto de modelos de lenguaje, declarado; nunca entra al motor como respuesta ni conocimiento. Enseña solo el modelo de utilidad con bancos
  gastados anteriores; este banco no se usó para enseñar ni ajustar nada.
- **Sectores repetidos (declarado antes de ejecutar).** Pese a la lista de exclusión, seis negocios repiten un sector de los bancos de enseñanza:
  `W3/n1` (farmacia), `W3/n3` (hotel), `W7/n1` (hotel boutique), `W7/n2` (clínica veterinaria), `W7/n3` (escuela de idiomas), `W7/n4` (taller de cerámica).
  Se informan también los resultados sin esos seis negocios (25 negocios de sector nuevo). Además hay tres centros comerciales y tres autopistas dentro
  del propio banco.
- Validación automática (`validacion_automatica.json`): estructura y JSON válidos en los 31; las claves de tipo `combinada` son en parte totales calculados
  (no copias literales) y algunas evidencias de W3, W4, W5 y W7 no son copia literal (el evaluador automático cuenta por claves; el juez lee todo).
  El banco no se leyó.
