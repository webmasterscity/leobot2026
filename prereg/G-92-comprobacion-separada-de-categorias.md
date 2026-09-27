# G-92 — comprobación humana separada de categorías

2026-09-27. Previo a descarga/lectura de `esp.testb` y código del evaluador.

## En palabras fáciles de entender

El último cambio mejoró el reconocimiento de nombres en los textos que usamos
para comparar ideas. Ahora lo comprobaremos con otro conjunto de textos humanos
que mantuvimos cerrado. El modelo será exactamente el mismo. Si la mejora no
se sostiene, no lo usaremos para enseñar qué clase de respuesta pide una pregunta.
Pasar esta comprobación tampoco demostraría todavía una mejora en el kiosco.

## Modelo, datos y controles

Modelo G-91 congelado, SHA
`3dcf0406c1a3bd512643c0fb0cbda2e56d419007d7f81ab0cf5960317af1f6e2`.
Mismos conteos y fórmula, sin retocar clases, palabras, fuerza de respaldo,
selección de datos ni método de puntuación. Fuente y antecedentes en G-89/G-91.

Descargar únicamente `https://www.cs.upc.edu/~nlp/tools/nerc/esp.testb.gz`,
desde el mismo equipo anotador. Límite 30 s/10 MiB; registrar URL, fecha, SHA
comprimido/descomprimido y costo en manifiesto con commit antes de evaluar.
Descomprimir para la huella no abre las etiquetas al diseñador. El lector
solo accede a su contenido después de `freeze-G92-comprobacion`.

Es test humano público previo al modelo, mantenido sin usar en esta sesión;
no material nuevo redactado después de congelar, ni reserva nueva del kiosco.
No se solicitará un redactor para sustituir esta fuente. PAR-6 permanece cerrado.

Comparar G-91, G-89 sin contexto léxico, palabra borrada y contexto confundido
con la misma permutación semilla 1 de G-91. Reutilizar evaluador G-89 (tramos,
clases, tokens, nombres completos no vistos, tokens nuevos, tiempos). Generalizar
solo la ruta de manifiesto del lector existente, conservando su comportamiento
por defecto; primero verificar las huellas de predicciones G-89 y G-91 en el
desarrollo gastado `testa`. No reinterpretar ni limpiar errores de anotación.

## Puertas y ejecución

Mismos cortes G-91 en testb: F1 ≥0,67, ≥0,02 sobre G-89, ≥0,01 sobre cada
control, recuperación ≥0,40 en ≥100 nombres completos no vistos en TRAIN.
Recarga en proceso nuevo/hashseed 1 exacta. No reajuste después de testb.

Si pasa, preregistrar un experimento de educación pregunta/clase y su utilidad
en bancos de negocios, con ablaciones y coste completo. No afirmar capacidad
operacional del kiosco ni promover el motor por este resultado de nombres.
Si falla, conservarlo y no integrar la variante G-91 ni enseñar preguntas con ella.

Adquisición ≤30 s pared, comprobación/reuso ≤10 s CPU, evaluación/recarga ≤60 s,
total ≤70 s, pared de ensayo ≤100 s, RAM conjunta ≤512 MiB. Sin nuevo aprendizaje.
Registrar costo anterior G-89/G-91 como previo, no como cero. Focal del lector
de manifiesto y trece rápidas; `freeze-G92-comprobacion` antes de ejecutar.
Resultados `results_v3/g92_separate_categories.json`. Motor/base estables intactos.
