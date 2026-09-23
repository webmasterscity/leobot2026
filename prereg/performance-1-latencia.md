# Preregistro de la batería fija de latencia

Fecha: 2026-09-22. Se establece sobre `estable-A-1` y se repetirá sin cambiar las consultas en cada tag estable. Es una prueba de rendimiento, no una demostración de capacidad nueva.

## Preparación y mezcla fija

Un solo proceso Python y, cuando el sistema lo permita, un solo núcleo de CPU. Se cargan exactamente 100 000 hechos distintos en la memoria de Leobot, además de una regla de inferencia corta, un procedimiento numérico aprendido y una relación lingüística aprendida desde tres frases. La semilla fija para elegir casos es la primera parte de `644c55528a5fd97a8822f719f70e11cfae242783`; no cambiará con futuros tags.

La batería cronometrada tendrá 20 consultas de hechos explícitos, 20 inferencias cortas, 20 ejecuciones de un procedimiento aprendido, 20 preguntas en español sobre la relación aprendida y 20 frases españolas desconocidas que deben abstenerse. Habrá 20 calentamientos previos fuera de la medición. Las consultas se intercalan en orden fijo; el resultado de cada consulta se verifica para impedir que una ruta rápida pero incorrecta parezca mejora. Se repite el proceso con `PYTHONHASHSEED=0`, `1` y `2` y se informa cada resultado y el peor.

## Medidas y regla de promoción

Se miden CPU y tiempo de carga, número final de hechos, RAM pico, latencia de pared p50/p95 por categoría y para el conjunto, y presupuesto de inferencia. Conocimiento ya adquirido: p95 ≤10 ms. Inferencia corta: p95 ≤200 ms. Ninguna consulta puede superar 1 s. En tags posteriores, ningún p95 puede empeorar más del 20 % respecto a `estable-A-1` sin una razón escrita. Un fallo impide crear un nuevo tag estable hasta corregirlo o registrar la excepción justificada. `timeout 45s` por ejecución; si la carga o una consulta excede el presupuesto, se registra como fallo, sin agrandar límites ni cambiar esta batería.

El script y sus resultados viven fuera de `leobot/`; el motor nunca los lee. El conjunto visible sirve como puerta de rendimiento, no como held-out de inteligencia general.
