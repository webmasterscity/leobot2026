# LEOBOT_STATE — continuidad de Leobot

## Estado de misión

- Actualizado: 2026-09-22 · commit 51bf9cd (motor congelado)
- Fases: A superada en su ensayo acotado · B en curso · C pendiente · D pendiente · E pendiente · F pendiente · G pendiente · H pendiente
- Fase en curso: B — detectar una operación ausente e inventar una primitiva meta verificable
- Último tag estable: `estable-A-1` · huella del motor: `644c55528a5fd97a8822f719f70e11cfae242783`
- Pruebas: 528 pasan · 2 fallos esperados · 0 fallos · Python 3.12.3
- Orden rápida: `timeout 40s env PYTHONHASHSEED=0 python3 -m unittest tests.test_meta_abstraction_a1 tests.test_meta_active_probe tests.test_v70 -q` · Orden completa: `timeout 90s env PYTHONHASHSEED=0 ./run_tests.sh --solo-pruebas`
- Preregistro activo: `prereg/B-1-operador-agregado.md` · estado: diseñado; tablero: `prereg/agi-board-1.md`
- Diseños intentados en la fase en curso: 1) operador agregado tipado → preregistrado, sin resultado
- Siguiente paso concreto: implementar B-1 según `prereg/B-1-operador-agregado.md`, sin perder la referencia de lenguaje 0/20 ni la puerta de latencia
- Bloqueos: ninguno
- Lectura (seguimiento): 0/4 en la sonda visible `experiments/user_text_probe.py` al cerrar A; no es una reserva independiente
- Tablero AGI (último tag): [resultado](results_v3/agi_board_estable-A-1.json) · MLQA español público 0/20, 20 no reconocidas · ARC-AGI-3 no evaluado · brecha frontier no comparable · obstáculo principal: adquirir significado de texto libre
- Latencia (último tag): 100 003 hechos; conocido p50 0,107–0,110 ms, p95 0,116–0,119 ms; razonamiento p95 0,279–0,282 ms; máximo <0,31 ms; RAM pico 199 520 KiB en tres semillas

## Historial de ciclos

- 2026-09-22 · El estado previo consolidó tres líneas históricas y dejó el lenguaje libre en 0/4. Sus detalles y fallos están en el historial Git anterior a `42c34a6`.
- 2026-09-22 · [A-1](prereg/A-1-subregla-meta.md), preregistrado en `42c34a6` antes de implementar. Motor congelado en `freeze-A-1`, commit `51bf9cd`. [Resultado A-1](results_v3/a1_meta_abstraction.json): tres órdenes, 160/160 aciertos con la pieza frente a 80/160 con idéntica información y sin reutilizarla; 10 aplicaciones candidatas de la pieza. Bot fresco y solo memoria: 80/160. Renombrado de símbolos: 160/160. Señal auxiliar invertida: 160/160, sin errores seguros. La primera reserva no midió la retirada después de reiniciar.
- 2026-09-22 · [A-1b](prereg/A-1b-controles-pendientes.md), preregistrado en `e4aa3e7` antes del evaluador `6badef1`. [Resultado A-1b](results_v3/a1b_controls.json): tres órdenes, vista dependiente retirada tras contraevidencia y reinicio; control intacto 160/160; tarea incompatible no promovió la pieza; señal invertida 160/160 antes y después de una observación real. Árbol del motor intacto. El controlador no pidió una prueba nueva en este caso porque su consulta activa solo cubre programas de rasgos, no piezas compiladas. Regresión completa: 528 pruebas, dos fallos esperados. Fase A superada **solo para la familia preregistrada**.
- 2026-09-22 · Costo A-1 por orden: 64 ejemplos fuente y 64 de aplicación; adquisición fuente 0,10–0,14 s de CPU, aplicación 4,91–4,95 s, ablación de aplicación 6,42–6,53 s. La búsqueda medida en A-1b consumió 5,00–5,11 s de CPU, incluidos 0,049–0,050 s de búsqueda de la pieza y 0,0025–0,0035 s de validación temporal; estas cifras son anidadas y no se suman a la adquisición. Consolidación de piezas 0,043–0,045 s, guardado/carga 0,015–0,016 s, consulta de 160 casos 0,0022–0,0025 s, intervención 0,00007–0,00008 s. Se exploraron 813–862 combinaciones planas en tratamiento y 3389–3713 en la ablación; la pieza examinó 10 aplicaciones. Ambos ensayos juntos tardaron unos 168 s de pared; pico 27 764 KiB. La adquisición fuente se amortiza al reutilizar la pieza; no se cuenta solo el costo de responder.
- 2026-09-22 · Sonda de lectura repetida antes del tag: 0/4 y código sin cambios. El ZIP y el PDF existentes son históricos; no se regeneran. Git es el registro de versiones.
- 2026-09-22 · [B-1](prereg/B-1-operador-agregado.md) y [latencia fija](prereg/performance-1-latencia.md) preregistrados antes de código; sin resultado ni tag nuevo.
- 2026-09-22 · Batería de latencia fija sobre `estable-A-1`: 100 003 hechos, cinco tipos de consulta, tres semillas de hash, 100 respuestas correctas por corrida; todas las puertas p95 y tope absoluto pasaron. [Semilla 0](results_v3/latency_estable-A-1_hashseed0.json), [1](results_v3/latency_estable-A-1_hashseed1.json), [2](results_v3/latency_estable-A-1_hashseed2.json). Pico 199 520 KiB. Esta mezcla acotada no demuestra rapidez en conversación o razonamiento abiertos. [Tablero AGI](prereg/agi-board-1.md) preregistrado antes de puntuar MLQA; sin tag nuevo.
- 2026-09-22 · [Tablero AGI](results_v3/agi_board_estable-A-1.json): 20 preguntas fijas del desarrollo público de MLQA español, 0/20 y 20 no reconocidas. ARC-AGI-3 es la versión pública reciente verificada, pero Leobot carece de interfaz para sus juegos; no evaluado. Sin comparación frontier en batería igualada. El principal obstáculo medido sigue siendo lenguaje abierto; B-1 se mantiene por su posible reducción de parches humanos, sujeto a evidencia.

## Resultados negativos y trampas conocidas

- **La fase A no equivale a abstracción general.** La pieza adquirida es una partición de dos comparaciones que se reutilizó en otra tarea de la misma estructura numérica. No se demostró transferencia entre dominios no isomorfos, invención de operaciones nuevas ni síntesis de learners. La preferencia por la pieza existente resolvió la señal auxiliar del ensayo, pero no prueba causalidad en general.
- La consulta de evidencia del MetaController funciona para reglas de rasgos; devolvió `no_learned_program` para la vista compilada de A-1. No atribuirle una intervención que no propuso. La observación la produjo el entorno.
- Lenguaje abierto: con cuatro frases reales del encargo, Leobot sigue en 0/4 respuestas. Puede aprender una forma de pregunta tras varias afirmaciones y dos preguntas independientes, pero no de una sola frase desconocida. Tres pruebas antiguas pasaron de «no reconocida» a «hipótesis pendiente»; todavía se abstienen de responder y no cuentan como tres capacidades.
- En 20 casos fijos del desarrollo público de MLQA español, el resultado fue 0/20 y todos quedaron sin reconocer. Esto amplía el diagnóstico lingüístico; tampoco es una reserva final ni demuestra que la solución sea una lista de palabras. El tablero aún carece de baterías públicas comparables para causalidad, conversación larga, planificación y herramientas.
- En una prueba histórica de transferencia entre estructuras distintas, el bot educado y el fresco necesitaron tres ejemplos cada uno: **sin transferencia**. No confundir renombrado de una misma estructura con transferencia entre modalidades.
- En documentos, a veces une dos frases casualmente próximas como un evento. Un filtro propuesto para evitarlo no mejoró el control porque otro filtro ya detenía esos casos. Prohibir todas las uniones también destruyó uniones válidas. La primera conclusión falsa sigue siendo posible.
- Una corrección de procedimiento se conserva, pero aún no distingue bien una excepción permanente de un cambio temporal. Una afirmación cruda desconocida puede terminar como evidencia provisional aunque no trate de una relación útil.
- Una prueba antigua de ahorro de búsqueda dio 590 o 594 estados al cambiar `PYTHONHASHSEED`; no usar una cifra única como costo exacto. La versión 0.10.0 eliminó otra dependencia del orden de los datos en una familia sintética, pero no todas.
- No se adoptó la ruta fija «cómo llego» de una rama histórica: podía inventar metas para destinos desconocidos. Tampoco se promueven variantes por su número de versión ni por contar más pruebas.
- Los resultados A-1 y A-1b son sintéticos y diseñados internamente. La comparación con [DreamCoder](https://arxiv.org/abs/2006.08381), [Stitch](https://arxiv.org/abs/2211.16605) y la [invención de predicados en ILP](https://ojs.aaai.org/index.php/AAAI/article/view/7113) muestra antecedentes claros de bibliotecas y piezas reutilizables. DreamCoder incluye guía neuronal y no se adopta su ruta operacional; Stitch aprende funciones de biblioteca por compresión de programas. La variante A-1 es mucho más limitada. Revisión breve de fuentes primarias: 2026-09-22. No se afirma novedad teórica.

## Capacidades existentes

- Motor Python 3.12, solo biblioteca estándar en `leobot/`, ejecución CPU. Los evaluadores, pruebas y resultados están fuera del motor y no son fuentes de respuestas operacionales.
- Hechos con procedencia, reglas y correcciones; inducción acotada de relaciones y construcciones de preguntas; lectura limitada de documentos; procedimientos numéricos aprendidos; planificación simbólica; guardado y carga en memoria y SQLite.
- MetaController con enrutamiento RBF, prioridades de recurso, selección de pruebas por información/costo, síntesis de programas de hasta tres predicados y piezas meta compiladas desde dos familias independientes. La pieza conserva fuentes y se retira junto con sus dependientes cuando pierde apoyo. Un resultado del enrutador solo ordena estrategias; no certifica la respuesta.
- El último ensayo estable demuestra reutilización dentro de una familia numérica, bajo código congelado. Aún falta inventar primitivas, sintetizar learners, aprender de documentos desconocidos una sola vez, transferir entre estructuras diferentes y sostener mejoras con poca intervención humana.

### En palabras fáciles de entender

Leobot aprendió una regla pequeña en dos grupos de ejemplos y luego la usó como pieza para resolver un problema más largo. En la prueba preparada acertó los 160 casos nuevos; la copia que recibió la misma información pero no podía usar esa pieza acertó 80. Cuando se contradijo una de las reglas de origen, dejó de usar la pieza, incluso después de apagarlo y volverlo a abrir. Esto es un avance limitado: no respondió ninguna de 20 preguntas en español tomadas de una colección pública. No hay base para decir que ya solo necesita información, que tiene inteligencia general o que supera a las personas.
