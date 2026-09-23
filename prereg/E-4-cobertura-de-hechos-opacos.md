# E-4 — Cobertura de respuesta dentro de hechos inducidos

Preregistrado antes del evaluador. E-3 creó 47 hechos al leer 20 pasajes nuevos, pero obtuvo 0 respuestas. En los documentos de enseñanza se observan argumentos que abarcan cláusulas enteras. Este diagnóstico separa tres causas: no se almacenó la respuesta; se almacenó enterrada en un argumento extenso; se almacenó en un argumento preciso pero la pregunta no accedió a él.

## Datos y ensayo

Repetir exactamente el currículo y los 20 artículos de E-3 con su semilla, que fueron seleccionados antes de ver sus respuestas. No añadir preguntas ni respuestas al bot. Congelar el árbol `freeze-E-4`, que debe ser idéntico a `freeze-E-3`; no se modifica el motor. Tras educar con 30 pasajes, crear una copia limpia por caso, ingerir el pasaje y examinar **solo hechos cuya fuente apunta a ese pasaje de prueba**. El evaluador, fuera del motor, comprueba si alguna respuesta humana normalizada es una secuencia completa de tokens dentro de un argumento. Registrar: cobertura en cualquier argumento, cobertura en argumento de hasta 8 tokens, longitud mediana del argumento que contiene respuesta, y estado de `respond`. La evaluación externa no enseña al motor ni traduce preguntas.

## Controles, decisión y presupuesto

Bot fresco por caso con el mismo pasaje, y bot educado. El pasaje crudo siempre contiene la respuesta en la batería extractiva; si no aparece en hechos del bot, es pérdida de representación. Si hay menos de 10/20 casos con respuesta en algún argumento educado, priorizar adquisición. Si hay al menos 10/20 pero menos de 5/20 en argumentos de hasta 8 tokens, priorizar segmentación y granularidad. Si hay al menos 5/20 argumentos cortos y 0 respuestas, priorizar acoplamiento pregunta-hecho. Estos umbrales solo dirigen el siguiente ensayo; no cierran E. Reinicio ya se comprobó en E-3. Contraevidencia e incompatible no discriminan una métrica de cobertura y quedan para un cambio de motor. Presupuesto: 30 documentos + 20 pruebas, 80 MiB descarga, 90 s CPU, 130 s pared, motor idéntico antes/después.
