# G-108 — Conocimiento general leído de Wikipedia en español (texto escrito por personas)

Fecha: 2026-09-29. Estado: diseñado (precede al código). Motor de partida: `1259b79`. Pedido del usuario (2026-09-29): ≥ 10× conocimiento
básico, general y cotidiano. Fase E/G: educación desde texto crudo.

## Qué fallo concreto resuelve
Sin texto de conocimiento general, `respond` contesta 0/102 (D1) y 0/106 (D2) preguntas cotidianas de redactores independientes. Las tres
rutas sobre relaciones léxicas (plantillas, lectura de relaciones verbalizadas, intersección) están refutadas en desarrollo
(`results_v3/g106_g107_desarrollo.md`): faltan hechos y definiciones escritos en lenguaje natural. La lectura literal del motor ya contesta
bien desde frases humanas («¿Para qué sirve un paraguas?» desde «El paraguas sirve para protegerse de la lluvia»).

## Fuente
Wikipedia en español en texto plano, `s3.amazonaws.com/datasets.huggingface.co/wikipedia_multilingual/raw/es.all` (2020, 3 389 106 618
bytes, SHA-256 `48f67d80244308f3e1010240f0cb93121a1d14e70f79093a5e21653125d0b643`). Viene **sin tildes ni eñes** («Espana»).
Es texto escrito por personas (CC BY-SA). Nada escrito por un modelo de lenguaje entra al motor.

## Mecanismo
1. **Selección de artículos** (fuera del motor, reglas generales, sin elegir temas a mano): (a) todo artículo cuyo título, sin tildes ni
   mayúsculas, es un lema de sustantivo común del léxico aprendido (AnCora) o del WordNet español; (b) los N artículos más largos entre
   los demás, con N para no pasar de 90 000 frases. De cada artículo, sus dos primeras frases de ≤ 40 palabras (definición y dato
   principal).
2. **Tildes restauradas por conteo**: cada palabra sin tilde toma la forma con tilde que en textos acentuados (AnCora `train`, SQuAD-es)
   aparece ≥ 90 % de las veces para esa forma sin tilde; si no hay forma dominante, se deja como está («esta»/«está» no se toca).
3. **Biblioteca compilada** (motor, `leobot/library.py`): las frases con su árbol sintáctico ya analizado se guardan en un archivo aparte
   (`build_library` / `attach_library`); al adjuntarla, sus filas se suman a lo leído y sus árboles a la caché, así que responder no
   analiza nada. La base principal no crece: las filas de biblioteca no se guardan con `save`.
4. **Respuesta acotada** (AIKR): si una pregunta tiene más de K filas candidatas para el análisis estructural, se miran solo las K con
   mayor coincidencia ponderada por rareza; K se fija en desarrollo por latencia, antes de congelar.
5. Nada cambia en `Bot.answer` (kiosco).

## Desarrollo
D1 (ya visto) para depurar; D2 (solo cifras agregadas vistas hasta hoy) como comprobación de desarrollo con conteo automático.
Se pasa a reserva solo si en D2: correctas ≥ 15 % de las contestables, correctas ≥ 60 % de las respuestas dadas, y `respond` p95 ≤ 200 ms.

## Experimento decisivo (reserva)
Motor congelado; banco nuevo de ≥ 300 preguntas cotidianas de ≥ 6 redactores independientes de ≥ 2 familias de modelo, escrito después
de congelar (encargo neutral `results_v3/saber/encargo_redactor_saber.md`, sin mensajes del usuario ni este preregistro). Juez ciego
doble con desempate (correcta / parcialmente correcta / abstención / equivocada / inventada).
Sistemas: sin biblioteca (línea base); con biblioteca; biblioteca de control con las mismas frases asignadas a otros artículos
(el título de cada artículo cambiado por el de otro: señal confundida); reinicio; `PYTHONHASHSEED` 0 y 1.

## Umbrales (fijados ahora)
1. Correctas (juez) ≥ 15 % de las contestables; línea base 0.
2. Entre las respuestas dadas, correctas o parcialmente correctas ≥ 80 %; inventadas 0 (toda respuesta cita una frase leída).
3. Control confundido: correctas ≤ un tercio del tratamiento.
4. Sin respuesta (datos particulares): ≥ 90 % abstenciones.
5. `respond` con la biblioteca: p95 ≤ 200 ms (razonamiento) y máximo ≤ 1 s; arranque (adjuntar) ≤ 30 s; RAM ≤ 1,5 GiB; kiosco
   idéntico respuesta por respuesta con y sin biblioteca.
6. Cantidad: frases de conocimiento general leídas ≥ 10 × las de hoy (0) — se informa el número.
Si 1 o 2 fallan, no se promueve.

## Presupuesto
Construir la biblioteca ≤ 60 min de CPU (análisis en 4 procesos); archivo ≤ 100 MiB.

## Riesgos declarados
- Wikipedia es enciclopédica: cubre mal lo muy cotidiano («¿qué se pone antes de los zapatos?») y bien lo geográfico o científico.
- La restauración de tildes puede dejar palabras sin tilde; nunca cambia el significado porque las formas ambiguas no se tocan.
- El texto es de 2020: datos que cambian (poblaciones) pueden estar desactualizados; las respuestas citan la frase.
