# G-11 — composición de acciones con dependencias aprendidas

Fecha: 2026-09-23. Preregistro anterior al código. Motor congelado `estable-E-1:leobot` = `1f3187f2ced4c97364503187d074815f33612326`. G-10 permanece fallido: 30,8–37,1 % de vectores completos frente al umbral 40 %, aunque las ocho acciones individuales superaron firmas barajadas. No se modifican sus resultados ni su criterio.

## Hipótesis y alternativa

Fallo observado: pistas de palabras para cada acción funcionan por separado, pero la combinación independiente acumula errores. Hipótesis: las dependencias entre acciones, aprendidas de demostraciones completas y evaluadas en bases distintas, mejoran la estructura conjunta. Alternativa sencilla: la mejora de acciones individuales es lo máximo que permite este texto; la coocurrencia de acciones solo memoriza patrones frecuentes de las bases de enseñanza. Un control sin dependencias y un control con firmas barajadas distinguen esas explicaciones. Si funciona, el siguiente ensayo deberá subir a **firma SQL completa** y fuente independiente; una victoria aquí no autoriza integración.

## Datos, partición y presupuesto

- Misma fuente y hash de G-10, sin abrir `dev_es`. Elegir tres semillas nuevas 521/587/641 con H0 y `0x69B`, reservar 20 % de bases completas y deduplicar SQL por base; no elegir consultas fáciles. SQL de enseñanza es demostración explícita; SQL de bases excluidas solo lo ve el evaluador tras predecir.
- El motor y sus configuraciones no cambian. Prototipo externo CPU estándar, ≤40 s CPU y ≤70 s pared por semilla, ≤256 MiB, p95 por pregunta ≤10 ms y ≤1 000 combinaciones examinadas. Repetir una semilla con `PYTHONHASHSEED=0/1`; presupuesto total ≤280 s pared.

## Tratamiento y controles

- Reutilizar el estimador léxico de G-10 **sin cambiar sus frases, apoyos ni pesos**. Aprender de las mismas demostraciones las frecuencias de pares de valores de acciones, con suavizado unitario; puntuar cada vector de ocho acciones como suma de evidencias léxicas locales más una suma normalizada de afinidades de pares. Enumerar los 256 vectores seguros; ninguna respuesta, verbo español o firma objetivo se programa a mano.
- Elegir fuerza de la afinidad solo mediante validación cruzada de tres grupos de **bases de enseñanza**; valores fijados `0, 0.25, 0.5, 1, 2`. Criterio: exactitud de vector completo, empate favorece menor fuerza. Volver a enseñar el modelo final con todas las bases de enseñanza. Registrar candidatos, CPU de validación y fuerza elegida. No ajustar con bases excluidas.
- Controles: G-10 independiente con la misma partición e información; firmas completas barajadas dentro de cada base antes de enseñar tanto léxico como afinidades; frecuencia del vector completo sin texto; prior por acción; bot fresco. El barajado conserva la estructura habitual de cada base y rompe el vínculo pregunta→acción. Guardar y cargar el modelo declarativo; contraevidencia sintética para una afinidad de pares; H0 antes/después.
- Renombrado: sustituir números y contenidos entre comillas **solo cuando la normalización G-10 produce los mismos tokens abstractos**. Reportar por separado el número de preguntas con comillas mixtas o mal formadas donde esa sustitución no conserva los tokens; permanecen en la exactitud principal. Exigir invariancia en todas las preguntas reconocibles y cobertura ≥99 %; cualquier caso no reconocible es limitación explícita, no acierto.

## Puerta de decisión

En cada semilla: ≥40 % de vectores completos correctos y ≥5 puntos porcentuales sobre el control G-10 independiente; ≥10 puntos sobre barajado y frecuencia sin texto; macro de acciones ≥0,65; al menos 10 casos en cada familia `join+filter` y `aggregate+order`, y ≥5 puntos de mejora en **una** de ellas sin degradar la otra más de 2 puntos. Reinicio, contraevidencia, renombrado reconocido, presupuestos y hash invariantes. Si el peso elegido es cero, o no hay ventaja sobre el control independiente, registrar no transferencia y no integrar. No cambiar puerta según resultados. Incluso si pasa, exigir un preregistro nuevo en otra fuente y firma completa antes de tocar `leobot/`.

## En palabras fáciles de entender

El ensayo anterior reconocía partes de una pregunta, pero se equivocaba al juntarlas. Ahora probaremos si aprender qué partes suelen ir juntas ayuda en bases nuevas. Si solo repite combinaciones frecuentes sin entender la pregunta, los controles lo mostrarán.
