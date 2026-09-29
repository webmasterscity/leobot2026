# G-106 y G-107 — resultados de desarrollo (2026-09-29, sesión de nube)

Motor de partida `fa15c4a`; código nuevo en `1391c6f` y siguientes (`leobot/knowledge.py`, cambios en `context.py`, `dialogue.py`,
`reading.py`, guardado JSON compacto). **Nada de esto se congeló ni se promovió.** Todo lo que sigue es desarrollo: el banco
`congelado_g103` ya está gastado y los bancos D1/D2 de conocimiento general son de desarrollo.

## Base reconstruida
`nube_base` 94 s de CPU, `nube_educar` 50 s; `base_kiosco_nube.json` SHA `b9aafc1bd9e1547cbb96e2ecb48f8690b7511bf16d89015597f45114e9eb6a15`
(la sesión anterior no registró el suyo; B0 da aquí 104/383 frente a 92/383 entonces, así que las bases difieren).

## 1. Familias de pares (paso 1 del traspaso anterior) — cerrado, negativo
Conteo automático en `congelado_g103`, directas + sí/no útiles de 383 (sin respuesta bien manejadas de 214):
| variante | útiles | sin respuesta bien |
|---|---|---|
| B0 | 104 | 214 |
| prefijos solos | **129** | 214 |
| modelo sin pares | **129** | 205 |
| pares abstractos (src, kind, shape) | 114 | 205 |
| todas las familias (375 508 pares) | 126 | 195 |
Ningún par aprendido mejora a los prefijos solos. **No repetir** la búsqueda de familias de pares palabra|palabra.

## 2. Diagnóstico por etapas (modelo sin pares; `experiments/g106_diagnostico.py`)
383 turnos: cita la unidad correcta 133 · elige otra teniendo la correcta entre las 8 candidatas **104** · elige bien pero calla 55 ·
ninguna unidad contiene las claves 41 · la correcta fuera de candidatas 38 · sin ninguna palabra en común 12.

## 3. G-106: saber general y cantidades en el kiosco — refutado en desarrollo (dos diseños)
Saber general: 260 142 relaciones leídas de WordNet español (MCR/OMW 1.4), ConceptNet 5.7 en español y Open Mind en inglés con
traducción humana de una palabra; 228 254 guardadas sobre 113 065 términos (9 s de CPU; base 78 MB en JSON compacto).
Conteo automático en `congelado_g103` (útiles / citas no útiles / citas sin dato):
| variante | útiles | no útiles | sin dato |
|---|---|---|---|
| prefijos solos | 129 | 101 | 50 |
| solo cantidades (rasgos + pares CMP) | 122 | 85 | 40 |
| solo saber (tasa por tipo de enlace) | 160 | 164 | 87 |
| saber + cantidades | 153 | 157 | 80 |
El +31 del saber viene **solo** de un umbral de cita más bajo (0,29 frente a 0,50). Curva de operación (`experiments/g106_curva.py`,
útiles con a lo sumo N citas malas):
| N malas | sin saber | saber | saber corregido por azar | saber + cantidades | cantidades |
|---|---|---|---|---|---|
| 50 | 108 | 106 | 100 | 105 | 103 |
| 100 | **149** | 134 | 139 | 134 | 144 |
| 150 | **162** | 155 | 156 | 153 | 158 |
| 250 | **180** | 175 | 178 | 174 | 179 |
A igual número de citas malas, ni el saber general (con o sin corrección por azar de la tasa por tipo) ni la comparación de cantidades
mejoran la elección. Por la regla de selección preregistrada ninguna variante nueva pasa, así que **G-106 no va a reserva**.
Tasas aprendidas por tipo (corregidas por azar): «sirve para» 0,26, «puede» 0,31, «derivado de» 0,32, «relacionado» 0,13,
«es un» 0,05, «es un» a dos pasos 0,003, antónimo 0,06–0,08 (los antónimos conviven en la misma unidad: «abierto… cerrado»).
**No repetir**: enlaces léxicos de WordNet/ConceptNet como puente en la mezcla o como rasgo del modelo; comparación de cantidades
como rasgos de candidata con pares «palabra junto al número | comparación».

## 4. G-107: responder conocimiento general — negativo en desarrollo
- Regla de transitividad preregistrada (cierre ≥ 0,05 y ≥ 5× la mediana): **ninguna relación se encadena** («es un» cierra 2,3 %
  de sus caminos en ConceptNet, porque no afirma todos los atajos).
- Banco de desarrollo D1 (120 preguntas, redactor independiente Sonnet; D2, 120, Haiku, aún sin usar): **0 correctas de 102
  contestables** con la ruta por plantillas (6 respuestas malas, p. ej. «Se usa ropa para anuncio»), 0 con la ruta por lectura
  (3 malas, p50 14,7 ms) y 0 sin saber general. Sondas propias: elige mal la relación («¿Qué es un perro?» → «Perro puede correr»),
  ruido de traducción («cuchillo para cortés»), «No» falsos con la ruta de lectura («¿La rueda es parte del coche?» → «No: rueda
  es parte de monopatín»).
- Supervisión distante para aprender qué relación pide una pregunta: en SQuAD-es enlaza 3 278 de 30 000 preguntas, casi todas
  «es un» (preguntas enciclopédicas); en Tatoeba 9 882 enlaces, conectores dominados por preposiciones; «para qué sirve» no aparece.
- Por qué: las preguntas cotidianas se piden **al revés** del almacén («¿Qué cubierto se usa para tomar la sopa?» → cuchara). Techo en
  D1: la respuesta está en el almacén en 86/102; enlazada directamente con alguna palabra de la pregunta en 40; con todas, en 6.
  Además faltan cuentas («¿Cuánto es 15 más 27?»), calendario y cifras («días de la semana»), geografía (capitales).
- Fuentes que faltan y el entorno bloquea: Wikipedia y Wiktionary en español, Tatoeba oficial, DBpedia, Hugging Face (403/000).
- Tatoeba vía GitHub (`doozan/spanish_data`, 160 913 frases): el filtro gramatical (presente, sujeto nominal, sin 1.ª/2.ª persona ni
  nombres propios) deja 21 318, de las que a ojo solo un tercio son saber general; no se usa como fuente de hechos.

## Qué se conserva
El almacén de saber general (cantidad: 0 → 228 254 relaciones de fuentes humanas) y las pruebas `tests/test_g106_saber.py`; los
interruptores `general_knowledge`, `number_compare` y `general_route` dejan el motor como antes cuando la base no trae saber.

## 5. G-107b: búsqueda por intersección — negativo en desarrollo ([preregistro](../prereg/G-107b-busqueda-por-interseccion.md))
Depuración en D1 (Sonnet, 102 contestables + 18 sin respuesta), tres versiones:
| versión | correctas | malas | contesta sin dato |
|---|---|---|---|
| intersección pura (≥ 2 enlaces, mejor único) | 2 | 29 | 9 |
| + la respuesta debe ser «un tipo de» (1–2 pasos) una palabra de la pregunta | 4 | 34 | 9 |
| + solo sustantivos como clase | 5 | 27 | 11 |
Comprobación preregistrada en D2 (Haiku, no mirado antes; 106 contestables + 14 sin respuesta), mecanismo fijo:
**3 correctas (2,8 %), 27 malas, 4 contestadas sin dato; precisión 3/34 (9 %)** frente a lo exigido (≥ 10 % y ≥ 60 %). No se pide reserva.
La intersección devuelve asociados, no respuestas («capital de Francia» → «estado»; «herramienta para clavar» → «reducir»):
el almacén léxico mezcla sentidos (lemas de verbo y sustantivo que coinciden, «es un» figurado de Wiktionary) y no guarda
los hechos que piden las preguntas cotidianas (capitales, cuántos, colores de cosas, qué hace un animal).
**No repetir**: responder preguntas generales por plantillas, por lectura de relaciones verbalizadas ni por intersección sobre
WordNet/ConceptNet. Las rutas quedan **apagadas por defecto** (`general_route = None`); la guarda contra el «No» por contraste
se conserva porque solo impide respuestas.
**Clasificación**: «no pudo» (entender qué pide una pregunta cotidiana y combinar restricciones con un almacén ruidoso) y «no sabía»
sin comprobar (faltan hechos: capitales, cifras, calendario, cuentas). El siguiente intento necesita fuentes de texto humano con
definiciones y hechos (Wikipedia/Wiktionary en español, bloqueadas en este entorno) o un mecanismo que aprenda la forma de las
preguntas cotidianas a partir de pares pregunta–respuesta humanos de ese tipo.

## 6. G-108: leer Wikipedia en español como biblioteca compilada — negativo en desarrollo ([preregistro](../prereg/G-108-leer-wikipedia.md))
Fuente hallada en un depósito público alcanzable: `s3.amazonaws.com/datasets.huggingface.co/wikipedia_multilingual/raw/es.all` (2020,
3 389 106 618 bytes, SHA-256 `48f67d80…b643`, sin tildes; también hay OSCAR en español en el mismo depósito). Tildes restauradas por
conteo en AnCora + SQuAD-es (6 295 formas con variante dominante ≥ 90 %).
- Biblioteca (`experiments/g108_biblioteca.py`, `leobot/library.py`): 1 082 987 artículos leídos; 23 575 con título de sustantivo común
  (AnCora/WordNet) y el resto por longitud; 46 808 artículos, **89 396 frases** (dos primeras de ≤ 40 palabras), 89 290 analizadas;
  44,8 MB; análisis 482 s de reloj en 4 procesos; adjuntar 21 s.
- Primer intento con detector de títulos defectuoso (perdía los artículos que empiezan por «El/La»): D1 1 correcta, 7 malas, máximo 13 s
  (índice construido en la primera pregunta). Corregido: índice al adjuntar, lector de tramos G-28 fuera de la biblioteca.
- D1 con la biblioteca corregida: **0 correctas, 9 malas**; p50/p95 14/31 ms. La lectura estructural elige mal entre muchas frases que
  contienen las palabras de la pregunta («capital de Francia» → frase de un municipio de Oise en «Alta Francia»).
- Comprobación preregistrada en D2: **1 correcta, 18 malas, 2 contestadas sin dato**; p95 65 ms, **máximo 2,1 s** (> 1 s). No pasa
  (exigido ≥ 15 % y ≥ 60 %); no se pide reserva.
- Búsqueda inversa por definición (diccionario inverso) medida en D1 con un guion: ingenua 8/76 correctas; estricta (todas las palabras en
  la definición, sustantivo preguntado presente, artículo único) 1/3. No se implementó en el motor.
**No repetir**: responder preguntas cotidianas desde las primeras frases de Wikipedia con la lectura estructural o con búsqueda inversa por
coincidencia de palabras. Lo que falta no es texto (ya lo hay) sino **recuperar la frase que habla de lo preguntado** entre decenas de
miles y saber qué tipo de respuesta se pide (un número, un lugar, una cosa). La biblioteca queda como mecanismo opcional (no se adjunta
por defecto; `attach_library`).
