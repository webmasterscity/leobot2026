# G-105 — Seguir las instrucciones del negocio con el mismo modelo de utilidad

Fecha: 2026-09-28. Estado: diseñado (precede al código). Depende de G-103 (`cb41148`).

## Qué fallo concreto resuelve
`Bot.load_context(texto, instrucciones)` guarda las instrucciones y `answer` **nunca las usa**. En los bancos, ≈ 10 % de los turnos dependen
de ellas: 165 de 243 turnos con evidencia en las instrucciones piden derivar (no confirmar reservas, no dar diagnósticos, remitir a una persona o
un teléfono), 34 piden responder según una instrucción y 44 preguntas sin respuesta esperan la instrucción de qué hacer cuando falta el dato.
Hoy esas preguntas se contestan «No lo sé», que el conteo automático da por correcto para «derivar» aunque el cliente se quede sin salida.
La misión pide explícitamente «sigue las instrucciones del negocio» y advierte no confundir abstenerse con obedecerlas.

## Por qué los mecanismos actuales no bastan
Las instrucciones no forman parte del índice ni de las candidatas. Añadirlas como unidades del texto mezclaría estadísticas y rompería
la interfaz (`context_units` no las incluye). Reglas por palabra («reserva», «diagnóstico») quedan prohibidas.

## Mecanismo
1. Las instrucciones se leen con la misma disposición (frases, elementos) y forman **su propio espacio**: índice, prefijos y BM25 propios
   (una vista del mismo objeto con las unidades de las instrucciones). Sus candidatas se puntúan con el **mismo modelo** de G-103, con un
   rasgo «viene de las instrucciones» y pares «palabra|origen» que enseña qué se parece a una instrucción.
2. Compiten por probabilidad calibrada la mejor candidata del texto y la mejor de las instrucciones. Si gana una instrucción y supera
   el umbral de cita, la respuesta la cita con una fórmula propia («Sobre eso, las indicaciones del negocio dicen: «…»»), estado
   `instruction`, con la unidad y su origen para quien integra.
3. **Cuando falta el dato**: un clasificador contado (Bayes ingenuo sobre las palabras de la frase) aprende qué frases de instrucciones
   dicen qué hacer cuando no se sabe algo; la etiqueta sale de las preguntas sin respuesta cuya evidencia está en las instrucciones. Si una
   frase supera su umbral (elegido con puntajes cruzados), la respuesta «No lo sé…» añade esa frase como salida («Las indicaciones del negocio
   para estos casos dicen: «…»»). Sin listas de palabras: lo aprende de los negocios de enseñanza.
4. Enseñanza (datos de enseñanza = mismos 9 bancos gastados, texto de modelos de lenguaje declarado): etiqueta de una candidata de las
   instrucciones = su frase contiene la evidencia del turno o está contenida en ella (≥ 3 palabras); de una del texto = contiene las claves
   (o la evidencia, si está en el texto). Los turnos cuya evidencia no está en ninguno de los dos no enseñan.
5. Interruptor `follow_instructions`; apagado, `answer` es exactamente el de G-103.

## Qué eliminaría si funciona
El «No lo sé» como única salida para las derivaciones y la advertencia de que la derivación está pendiente.

## Experimento que distingue las hipótesis
Mismo banco nuevo que G-103/G-104 y mismo juez doble, con una **rúbrica nueva declarada antes de verlo** para turnos de acción `derivar`
o tipo `instruccion`: `util` (la respuesta lleva al cliente por la salida que dice la instrucción: contacto, persona o pasos), `honesta`
(dice que no lo sabe o no puede, sin la salida), `enganosa` (contradice la instrucción, por ejemplo confirma lo que no se debe confirmar,
o manda a un contacto equivocado). En este subconjunto un «No lo sé» sin salida es `honesta`, no `util`. Se informa también con la rúbrica
anterior (abstención correcta). Sistemas: B0, G-103 sin instrucciones (interruptor apagado), G-105, instrucciones barajadas (las de otro
negocio del banco: señal confundida).

## Umbrales de éxito (fijados ahora)
Con el juez, entre los turnos `instruccion` y `derivar`:
1. Útiles de G-105 ≥ útiles de G-103-sin-instrucciones + 25 puntos porcentuales, y > instrucciones barajadas + 25 puntos.
2. Engañosas ≤ 5 % de los turnos de este subconjunto; inventadas: 0.
3. Directas + sí/no y sin respuesta (no derivar): sin cambio peor que 1 punto frente a G-103 (mismo juez).
4. Al faltar el dato con instrucción de salida: la respuesta trae la salida correcta en ≥ 60 % de las preguntas sin respuesta que la piden.
5. Latencia de `answer` con instrucciones: p95 ≤ 10 ms.

## Riesgos declarados
Las instrucciones están escritas para el asistente, no para el cliente: citarlas es correcto pero tosco («pídale el número de habitación…»).
Generar la frase para el cliente exige lenguaje generado, que Leobot no tiene; se deja al integrador con los campos estructurados.
El texto de instrucciones y de preguntas viene de modelos de lenguaje.
