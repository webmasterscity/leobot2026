# G-17 — eliminar normalizaciones repetidas de una misma interpretación

Fecha: 2026-09-23. Preregistro anterior al cambio de motor. H0 = `estable-E-1:leobot` = `1f3187f2ced4c97364503187d074815f33612326`. G-16 se interrumpió tras 212/1235 artículos de enseñanza por ≥95 s CPU. El [perfil posterior](../results_v3/g16_education_profile.json) de solo tres artículos observó 120 002 llamadas a `normalize` para diez interpretaciones y 4,281 s acumulados allí, aunque `cProfile` infla tiempos absolutos.

## Hipótesis y alternativa

Fallo observado: `Language.parse` pasa la misma entrada a cientos de `Construction.parse_candidates`, y cada candidato vuelve a normalizarla. Hipótesis: normalizar la entrada una sola vez por interpretación y reutilizarla también en variantes reescritas reduce CPU **sin modificar** salidas. Alternativa: enumerar regex y reescrituras domina el costo real, por lo que evitar normalizaciones no abarata suficientemente la educación. Solo se cambia el transporte de texto ya normalizado, no gramática, límites, pesos, orden, hechos o criterios de confianza. Si funciona, podrá retirarse esa repetición interna; si falla, se revierte y se conserva el perfil.

## Comparación causal y corpus fijo

Antes de editar `leobot/`, medir H0 con un script externo sobre el mismo [REDFM español `train`](https://huggingface.co/datasets/Babelscape/REDFM/blob/7fab33bee528dc1dd09d90f788afc93d35fd71b3/data/train.es.jsonl), SHA-256 `3af0fff77d7bb3d2907839e1db8e33d56b8e84ae17309f056257f240ec8127b8`. Usar solo artículos de educación de la partición G-16 semilla 911, sin tocar excluidos. Enseñar 4 171 hechos y los 472 pares de oración/marco candidatos con el mismo procedimiento G-16. Medir 24 frases fijadas por orden de la fuente (12 enseñadas y 12 de otros párrafos de educación) y después los primeros 30 artículos de educación. Guardar hash de resultados completos de interpretación e ingestión, contadores, CPU de enseñar, CPU de interpretar, CPU de ingerir, p50/p95, RAM. No guardar texto fuente.

Después del cambio mínimo, repetir **exactamente** fuentes, selección y orden. Control/ablación = H0; tratamiento = motor con normalización compartida. Las salidas completas, construcciones aceptadas y nuevos hechos deben ser idénticos byte a byte tras serialización canónica en `PYTHONHASHSEED=0`. Repetir controles rápidos y una pasada `PYTHONHASHSEED=1` para detectar dependencia de orden. No usar los artículos excluidos de G-16 para ajustar. El hash del motor candidato será H1 antes/después de su ensayo; no llamar aprendizaje a un cambio de código.

Puerta: CPU de interpretación ≥5 veces menor y CPU de ingestión de 30 artículos ≥3 veces menor que H0; p95 de interpretación ≤10 ms, cada artículo de ensayo ≤1 s, ninguna divergencia de salida, CPU total de cada medición ≤60 s, pared ≤90 s, RSS ≤256 MiB. Si no pasa, revertir cambio y registrar hipótesis refutada. Si pasa, ejecutar regresión completa y la sonda fija con 100 003 hechos; no crear tag si falla una prueba, si algún p95 del motor supera presupuesto o empeora >20 % respecto de `estable-E-1` sin justificación. Aun con puerta pasada, repetir G-16 bajo **nuevo preregistro** y nueva huella antes de atribuir capacidad documental; optimizar CPU solo habilita medirla.

## En palabras fáciles de entender

Hoy Leobot vuelve a preparar la misma frase miles de veces mientras intenta entenderla. Probaremos si prepararla una vez hace que lea más rápido sin cambiar ninguna respuesta. Si ahorra suficiente tiempo, podremos repetir la prueba de aprendizaje con documentos reales; la rapidez por sí sola no demuestra que comprenda.
