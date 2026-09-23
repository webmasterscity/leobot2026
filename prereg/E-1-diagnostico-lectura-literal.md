# E-1 — Diagnóstico externo de lectura literal

Preregistrado antes de escribir el evaluador y antes de modificar el motor. Es un diagnóstico para escoger el mecanismo de la fase E; por sí solo no puede superarla.

## Fallo y alternativas

El tablero público obtuvo 0/20 en preguntas españolas de MLQA después de leer cada pasaje. Hipótesis principal: el motor no adquiere relaciones de una sola exposición a prosa desconocida. Alternativa: sí adquiere información útil, pero no entiende las preguntas. El experimento separa hechos añadidos, respuesta antes y después de leer y coincidencia exacta con la respuesta humana. Si aparecen hechos pertinentes y falla la respuesta, se favorece la segunda explicación. Si no aparecen hechos y la respuesta falla, se favorece la primera. Una coincidencia textual sin traza no prueba comprensión.

## Familia, partición y reserva

Usar `MLQA_V1/dev/dev-context-es-question-es.json` de la publicación original de MLQA, archivo SHA-256 `246e8089933d13007fe80684d5c5c0713d6834cf8b3b4a0ec7c66f0a0d2baac8`. Los pasajes provienen de Wikipedia y se redactaron independientemente del parser. Excluir los 20 identificadores fijos del tablero AGI. Ordenar por identificador y seleccionar 20 preguntas adicionales con `random.Random(int(<huella del árbol leobot>[:8],16)).sample(...)`. Congelar y etiquetar el motor antes de seleccionar. Conservar solo identificadores, estados y métricas en el resultado; las respuestas humanas se usan exclusivamente en el evaluador. Esta partición de desarrollo disjunta es reserva estructural de diagnóstico, no reserva final independiente.

## Ensayo y controles

Para cada caso, crear un bot fresco y preguntar antes de la lectura; después pasar el pasaje crudo a `ingest_document_text` y hacer la misma pregunta por `respond`. El bot no recibe respuestas, etiquetas ni traducción semántica. Registrar hechos añadidos, promociones, estados, coincidencia exacta normalizada, respuesta con traza, CPU por lectura y respuesta, RAM pico. La pregunta previa es control fresco y prelectura. Como control de solo memoria, comparar con extracción literal del pasaje hecha fuera del motor, sin llamarla aprendizaje ni usarla para responder; si la coincidencia de una cadena supera al motor, la pérdida puede estar en el análisis. En esta primera prueba no se entrenará una regla ni habrá intervención: ablación, misma información sin learner, confounder, contraevidencia y reinicio no discriminan entre las dos causas propuestas. Quedan obligatorios para un mecanismo posterior. Repetir con semillas de hash 0, 1 y 2 si varía una métrica.

## Umbral y presupuesto

Decisión: predominio de cero hechos nuevos junto con cero respuestas con evidencia favorece el bloqueo de adquisición; hechos nuevos en al menos 5/20 y cero respuestas con evidencia favorecen el bloqueo de interpretación de preguntas. Cualquier resultado mixto se registra sin forzar conclusión. Tope: 20 casos, 120 s de pared, 60 s de CPU por corrida, 40 MiB de archivo descargado; una corrida inicial. No se modifica el motor durante el ensayo. `git rev-parse freeze-E-1:leobot` y el árbol de trabajo del motor deben coincidir antes y después.

## Admisión de mecanismo

Ningún subsistema se añade en E-1. El resultado decidirá si se preregistra un mecanismo de adquisición o de interpretación. Si uno funciona, se buscará retirar rutas duplicadas de lectura y se medirá su costo completo.
