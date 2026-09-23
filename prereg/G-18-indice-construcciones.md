# G-18 — índice conservador de construcciones lingüísticas

Fecha: 2026-09-23. Preregistro anterior al motor. H0 `estable-E-1:leobot` = `1f3187f2ced4c97364503187d074815f33612326`. G-17 compartió la normalización y conservó salidas, pero solo redujo CPU de interpretación 3,17× y de ingestión 2,25×; p95 siguió 59–63 ms, por lo que fue revertido. El perfil G-16 registró 114 977 intentos de construcción para diez interpretaciones, muchos de ellos imposibles por falta de texto fijo.

## Hipótesis y alternativa

Hipótesis: cada construcción con un fragmento literal de ≥3 caracteres exige que al menos una subcadena de tres caracteres de ese fragmento aparezca en la frase ya normalizada. Un índice invertido por esa subcadena permite omitir candidatos imposibles, preservando fallback para construcciones sin fragmento largo. Aplicarlo también a variantes de reescritura, siempre en el orden anterior. Compartir una normalización por frase como en G-17 es parte del tratamiento. Alternativa sencilla = G-17 sin índice; la reducción restante vendría de reescrituras, regex o lógica documental, y el índice no aportaría suficiente.

Mecánica universal, sin palabras españolas, predicados, nombres de benchmark ni respuestas codificadas: extraer los trozos literales de `Construction.surface` entre marcadores de argumento, elegir una subcadena de longitud tres cuyo listado actual sea el más corto, guardar índice de posiciones al enseñar. Si no hay trozo seguro, incluir la construcción en fallback. Un candidato omitido debe ser **demostrablemente incapaz de coincidir** con el texto normalizado; si hay duda, usar fallback. Reconstruir índice desde ejemplos al cargar, sin persistir código ni aceptar regex del exterior. Si pasa, elimina la enumeración total en la ruta habitual; si falla, revertir íntegramente.

## Experimento, controles y puerta

Reusar exactamente [baseline G-17 H0](../results_v3/g17_baseline_hashseed0.json), script, corpus REDFM español `train` fijado, 4 171 hechos/393 construcciones aceptadas, 24 frases y 30 artículos de **educación**, sin abrir excluidos. Control adicional = [G-17 normalizar solo una vez](../results_v3/g17_candidate_hashseed0.json), que no pasó. Los hashes completos de respuestas, hechos, enseñanza y estados deben coincidir con H0. Medir CPU total, de parse y de ingestión, p50/p95, máximo por artículo, RSS y número de construcciones examinadas frente a candidatas filtradas; repetir `PYTHONHASHSEED=0/1` y pruebas rápidas/focales. H2 congelado (árbol Git limpio) durante cada medición.

Puerta preregistrada: ≥10× reducción de CPU en las 24 interpretaciones respecto H0, ≥5× en 30 artículos, ≥3× y ≥2× respectivamente frente a G-17; p95 de interpretación ≤10 ms y cada artículo ≤1 s; respuestas **idénticas**; medición CPU ≤60 s, pared ≤90 s, RSS ≤256 MiB. Si no pasa, revertir y conservar resultado negativo. Si pasa, ejecutar regresión completa y sonda fija con 100 003 hechos; ningún p95 supera presupuesto ni empeora >20 % frente al último tag sin justificación. Solo entonces crear tag estable. Una mejora de búsqueda no es aprendizaje ni solución de lectura abierta; reabrir G-16 requiere otro preregistro con huella H2 y controles completos.

## En palabras fáciles de entender

Hoy Leobot revisa muchas formas de frases que contienen palabras ausentes de la pregunta. El índice le permitirá saltarse esas formas sin cambiar ninguna respuesta. Mediremos si el ahorro alcanza para leer documentos reales dentro del tiempo permitido.
