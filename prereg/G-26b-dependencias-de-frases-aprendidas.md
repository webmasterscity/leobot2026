# G-26b — retirar hechos que dependen de una frase aprendida

Fecha: 2026-09-23. Sigue el resultado G-26; preregistro nuevo **antes** de corregir el motor. Árbol G-26 `6a2f795ff847b7aaf5787258579abf822988c118`.

## Fallo, hipótesis y alternativa

G-26 pasó su puerta acotada, pero un uso normal reveló que `respond("dana cuida ciro")` crea un hecho mediante una construcción inducida y una respuesta contradictoria posterior retira la construcción **sin retirar ese hecho**. El fallo procede de perder la procedencia de la construcción que produjo cada análisis. Hipótesis: conservar el índice de construcción que ganó la interpretación y registrar solo los IDs de hechos nuevos que dependen exclusivamente de una construcción G-26 permite invalidarlos al retirar la hipótesis. Alternativa: registrar solo el predicado/superficie retiraría hechos independientes; no sirve. Si el rastreo falla, no promover G-26 ni crear tag.

## Experimento y reserva

Desarrollo visible: la frase anterior, una variante de roles invertidos y un caso donde el mismo hecho está apoyado independientemente por otra fuente. Evaluación tras congelar motor y evaluador: 12 familias nuevas generadas con semilla derivada de `git rev-parse <commit>:leobot`, sin reutilizar la semilla de G-26. Conservar la estructura de G-26 y su control pasivo, pero **usar la construcción aprendida en `Bot.respond` con entidades nuevas** antes de contraevidencia. Verificar que la corrección retira los hechos creados exclusivamente por ella y las consultas que los usaban, mientras conserva hechos agregados por una fuente independiente; confirmar después de guardar/cargar. Incluir renombrado total de símbolos, roles invertidos, respuesta sí/no alternada y caso sin negación explícita. No escribir nombres de la familia en el motor.

Tratamiento: rastreo por construcción en análisis directo y reformulado, más retiro por ID. Ablación: misma observación y respuesta, pero se borra el registro de dependencias antes de corregir; deberá conservar el hecho erróneo y fallar el criterio de limpieza. Fresco, solo memoria, mismo dato sin learner, incompatible y señal confundida siguen los de G-26. La corrección nunca borra hechos con otro ID/fuente ni un hecho que más tarde haya sido afirmado independientemente por otra construcción. Si hay análisis lingüístico ambiguo o procedencia insuficiente, no atribuir exclusividad ni almacenar el hecho automáticamente.

Puerta conjunta: ≥10/12 familias siguen eligiendo la pregunta discriminante y aprendiendo el significado correcto; **12/12** retiran el hecho dependiente y su respuesta tras contraevidencia, **12/12** preservan el apoyo independiente, **12/12** reinicios mantienen tanto el rastro como la invalidación, renombrado 12/12; ablatado 0/12 retiradas; ningún hecho se registra cuando el análisis es ambiguo. Motor idéntico antes/después de cada ensayo. Límite 30 s CPU, 45 s pared, 128 MiB RSS, 128 hechos por predicado y 256 opciones. Medir adquisición, selección, feedback, almacenamiento, invalidación, persistencia e inferencia por CPU, opciones, ejemplos y RAM. Dos hashseeds 0/1 si la primera corrida pasa. No ajustar umbrales tras reserva. Si pasa, ejecutar regresión completa antes de un tag; anotar explícitamente que dependencias en otros learners aún necesitarían auditoría independiente.

## En palabras fáciles de entender

Leobot aprendió a entender una frase nueva preguntando por un ejemplo. Pero si luego descubrimos que la entendió mal, puede quedar guardado un dato que nació de ese error. Ahora comprobaremos que recuerda de dónde salió cada dato, lo borra al corregirse y conserva los datos que llegaron por una fuente independiente.
