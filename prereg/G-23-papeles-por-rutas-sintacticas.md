# G-23 — ¿se transfieren papeles por rutas sintácticas aprendidas?

Fecha: 2026-09-23. Preregistro anterior al evaluador. Motor H0 `1f3187f2ced4c97364503187d074815f33612326`.

## Fallo, mecanismo y alternativa

G-19/G-20 no superaron tipos de entidades y G-21 reconoció solo 5/75 pares con fragmentos literales. La [puerta G-22b](../results_v3/g22b_ancora_source_hashseed0.json) halló 14 065 oraciones españolas con texto y estructura sintáctica alineados, 69 007 argumentos válidos y papeles recurrentes entre miles de lemas. Hipótesis: una **ruta de dependencias** entre verbo y argumento, aprendida de episodios anotados, puede asignar los papeles A0/A1/A2 en verbos no vistos mejor que la posición lineal o una sola etiqueta sintáctica. Alternativa: `nsubj`, `obj` y la posición ya explican el resultado; la ruta añade complejidad sin transferencia. Si falla, no integrar el mecanismo.

[UP Spanish AnCora](https://github.com/UniversalPropositions/UP_Spanish-AnCora) transfiere papeles de PropBank inglés y advierte errores; [UD Spanish AnCora](https://github.com/UniversalDependencies/UD_Spanish-AnCora) ofrece el árbol sintáctico. [BabyDS 2026](https://researchportal.hw.ac.uk/en/publications/babyds-visually-grounded-grammar-induction-with-online-curriculum/) motiva operaciones léxicas compuestas desde significados ofrecidos, pero no demuestra esta hipótesis. **El árbol UD de reserva es un dato externo dado por el evaluador.** Si el ensayo pasa, solo demuestra aprendizaje *condicional a ese árbol*, no lectura autónoma desde texto crudo ni una capacidad operacional de Leobot.

## Datos y reserva congelada

Usar solo los dos archivos `train` y revisiones/hashes fijados en G-22b; excluir las 222 oraciones cuyos IDs de tokens difieren. No abrir `dev/test` oficiales. Obtener documento del `sent_id` quitando sufijo `-s` seguido de dígitos; si falta, excluir y contar. Para tres semillas 1361, 1423 y 1487, derivar asignación sin mirar papeles: tomar los primeros 8 bytes de SHA-256 de las cadenas UTF-8 `H0:semilla:doc:<id>` y `H0:semilla:lemma:<lema>` como enteros sin signo en orden grande, módulo 4. Educación = documentos y lemas con residuo distinto de cero en ambas pruebas; reserva = documentos y lemas con residuo cero en ambas; casos cruzados se ignoran. Así no se comparte ni documento ni lema verbal entre educación y reserva. Evaluar solo predicados UP cuyo token UD tenga `UPOS=VERB`, lema válido, token alineado y árbol sin ciclos; registrar exclusiones. Ejecutar primero 1361, repetirla con `PYTHONHASHSEED=0/1`, detener las demás si falla la puerta.

Para cada predicado, considerar cada token normal distinto de él con ruta sintáctica de longitud 1–3 como cabeza candidata. Etiqueta positiva A0/A1/A2 solo si `UP:ARGHEADS` atribuye ese papel a ese token; si recibe dos papeles nucleares distintos, excluir el candidato y contar. Otros candidatos son `NONE` (una aproximación: UP puede omitir argumentos). Reportar qué proporción de cabezas gold A0/A1/A2 queda dentro de longitud 3: el sistema no puede recuperar las demás. Esta es una prueba de detectar y asignar cabezas, no de delimitar tramos completos.

## Aprendiz declarativo y controles

La hipótesis es una tabla aprendida, sin lemas, palabras, sentidos ni respuestas en el código: clave `(ruta de pasos arriba/abajo con etiquetas UD, clase gramatical de cabeza)` → A0/A1/A2. Si no tiene apoyo suficiente, retroceder a la ruta sola. Una regla se promueve con ≥8 episodios, ≥5 apoyos de un único papel y ≥60 % de todos sus episodios para ese papel; de otro modo produce `NONE`. Claves y reglas se construyen solo de educación. Presupuesto de ruta ≤3 y de candidatos ≤2 millones por semilla; no subirlo viendo reserva. Interpretación por diccionario compilado, sin buscar todas las reglas por consulta.

Controles con **mismos candidatos y episodios**: posición izquierda/derecha + clase gramatical de cabeza; una sola etiqueta de dependencia del candidato + clase gramatical; papeles barajados entre candidatos dentro de cada predicado conservando sus cantidades; solo memoria exacta de oración/predicado; fresco. Todos usan la misma condición de apoyo/promoción. Renombrado de todas las palabras de entrada (conservar solo árbol, posiciones y clases) debe producir las mismas salidas. Guardar/cargar tablas del tratamiento debe producir salidas idénticas. Un ensayo posterior con interfaces normales deberá probar contraevidencia; este prototipo externo no promueve conocimiento del bot.

## Métricas, puerta y costo

Medir micro-F1 de papeles positivos y F1 individual A0/A1/A2 sobre **todos** los candidatos de reserva, no exactitud dominada por `NONE`; precisión/recobrado, predicados con papeles correctos, cobertura de cabezas gold, candidatos/rutas/abstenciones, documentos/lemas nuevos y p50/p95 por predicado. Reportar CPU de descarga, adquisición, búsqueda/formación, validación y predicción, pared y RAM pico. En **cada** semilla: ≥400 predicados y ≥20 lemas reservados, ≥500 cabezas gold representables; micro-F1 ≥0,65 y ventaja ≥0,10 absoluta frente al mejor control; A0 y A1 F1 ≥0,60, A2 ≥0,40; barajado al menos 0,15 por debajo; renombrado/reinicio exactos y p95 de predicción ≤10 ms. CPU total ≤30 s, pared ≤60 s, RSS ≤256 MiB y ≤2 millones de candidatos; H0 y evaluador congelados. Si 1361 falla, registrar y detener 1423/1487. Sin regresión completa ni tag por un prototipo externo.

Si pasa, preregistrar integración en el learner DSL y un siguiente ensayo desde texto crudo sin árbol UD entregado, con persistencia, corrección y 100 000 hechos. Ese paso deberá medir el costo de aprender o adquirir la estructura sintáctica, que aquí es información regalada.

## En palabras fáciles de entender

La colección marca quién participa en cada acción de una frase. Probaremos si Leobot podría aprender a reconocer esos papeles siguiendo la estructura de la oración, incluso con verbos nuevos. Compararemos con reglas sencillas basadas en el orden de las palabras y con ejemplos mezclados. En esta primera prueba la estructura viene dada; entenderla directamente del texto será otra prueba.
