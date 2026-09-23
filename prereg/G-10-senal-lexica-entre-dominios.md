# G-10 — señal léxica entre dominios desde demostraciones completas

Fecha: 2026-09-23. Preregistro anterior al código de G-10. El árbol del motor queda congelado en `1f3187f2ced4c97364503187d074815f33612326` (`estable-E-1:leobot`). Esta es una **puerta de viabilidad**, no una afirmación de comprensión ni un ensayo final.

## Fallo e hipótesis

G-9c promovió cero reglas: solo 0/1/2 de 259/186/355 contrastes locales reunieron apoyo entre dos bases y ninguno pasó precisión. Causa candidata: exigir que dos frases difieran en un solo tramo y una sola ranura descarta casi toda la evidencia de demostraciones completas. Hipótesis G-10: las secuencias de 1–3 tokens contienen señal compositiva sobre las ocho acciones de consulta aunque no haya pares mínimos. Alternativa sencilla: la correlación entre palabras y acciones se debe a bases o traducciones concretas y desaparece en bases nuevas. La prueba compara un modelo explícito de frases contra etiquetas barajadas **dentro de cada base** y contra la acción mayoritaria, con bases completas excluidas. No se relajarán los criterios de G-9c.

La [investigación BabyDS de 2026](https://www.mdpi.com/2226-471X/11/5/99) motiva aprender hipótesis léxicas simbólicas a partir de pares expresión/significado formal. Su gramática, su entorno y sus significados de enseñanza están diseñados; aquí solo se toma la pregunta de si existen pistas léxicas transferibles. Ningún modelo neuronal entra en Leobot.

## Familia, datos y partición

- Fuente fijada: `train_es.json` de G-9b con hash SHA-256 ya verificado allí; preguntas y SQL explícitos son **instrucción** para el aprendiz. Una consulta SQL por base, mismas 111 bases con ≥20 SQL distintos. SQL de comprobación pertenece solo al evaluador.
- Tres semillas nuevas 311, 389 y 457, mezcladas con los primeros ocho dígitos de H0 y la constante de partición `0x69B`; reservar las primeras `max(20, round(0.2*n))` bases completas. Derivar particiones **después** del preregistro. Variar `PYTHONHASHSEED=0/1` en al menos una semilla. Son particiones de desarrollo de una fuente conocida, no una reserva externa.
- Los ocho nombres de acciones vienen del extractor SQL ya existente: `aggregate`, `filter`, `group`, `join`, `limit`, `nested`, `order`, `set`. El extractor etiqueta solo enseñanza y evaluación; no se entrega una lista de palabras españolas al aprendiz. Abstraer números y valores citados igual que G-9c.

## Mecanismo mínimo y controles

- Tratamiento: recoger todas las secuencias contiguas de 1–3 tokens de **cada pregunta completa**, contar presencia, acción verdadera/falsa y bases distintas. Aceptar una secuencia solo con presencia en ≥3 bases y ≥8 preguntas. Estimar por acción una razón de verosimilitud con suavizado unitario; conservar hipótesis positivas y negativas con su soporte. En predicción sumar el prior y, para evitar triple conteo de secuencias solapadas, sumar solo la pista de mayor magnitud por acción. Presupuesto de hasta 1 000 hipótesis examinadas y 10 ms por consulta. Ninguna pista puede ser nombre de base, identificador de benchmark o etiqueta de respuesta.
- Control confundido: permutar las firmas SQL completas dentro de cada base de enseñanza antes de contar; conserva frecuencia de acciones por base y texto, rompe correspondencia local. Control fresco: prior mayoritario sin enseñanza. Control G-9c: sus resultados previos se reportan como referencia diagnóstica, no como comparación sobre idénticas particiones.
- Comparar exactitud de vector completo de ocho acciones y promedio de exactitud equilibrada por acción que tenga ambas clases en cada partición. Registrar además `join+filter`, `aggregate+order`, acuerdo en renombrado de valores, número de pistas, CPU de adquirir e inferir, candidatos, p50/p95 y RAM pico. Repetir tras guardar/cargar modelo declarativo; H0 antes/después.
- Contraevidencia: añadir a una copia del modelo ejemplos sintéticos de **una secuencia abstracta sin palabra de la prueba** y acción invertida en ≥3 bases ficticias, reestimar desde los datos y comprobar que su puntuación cambia de signo. Es una prueba local de actualización, no prueba de revisión de conocimiento del motor.

## Puerta, costo y falsación

En **cada** semilla, el tratamiento debe obtener exactitud equilibrada macro ≥0,65 y superar por ≥0,10 al mejor entre barajado y prior; además debe acertar el vector completo de acciones en ≥40 % de preguntas y superar el barajado por ≥0,10. Exigir que al menos dos acciones no constantes tengan mejora ≥0,10 cada una. Si el barajado iguala o supera al tratamiento, o si la señal aparece solo en una base, la hipótesis queda refutada para esta fuente. Si pasa, preregistrar **otro** ensayo de composición hacia firma completa y generalización más allá de este corpus antes de tocar `leobot/`. No se promoverá una simple puerta de correlación.

Presupuesto por semilla: ≤30 s CPU, ≤60 s pared, ≤256 MiB RAM, p95 ≤10 ms; tres semillas y dos órdenes de hash dentro de 240 s pared total. Toda salida sin terminar por presupuesto cuenta como fallo, no se ajusta el umbral a posteriori. La serie E/G muestra que pasar tests internos no demuestra lectura abierta; `dev_es` permanece cerrado.

## En palabras fáciles de entender

Antes buscábamos dos preguntas casi iguales para aprender qué significaba una frase; casi nunca aparecieron en bases diferentes. Ahora veremos si las palabras de muchas preguntas completas permiten aprender una pista que sirva en bases nuevas. Si las pistas no superan a palabras mezcladas con respuestas equivocadas, no habremos demostrado aprendizaje útil.
