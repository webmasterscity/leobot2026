# G-102 — contexto aprendido: prueba terminada

28-09-2026. Resultado negativo para los requisitos completos; sin promoción.
[Preregistro](../prereg/G-102-contexto-aprendido.md), [enseñanza](g102_training.json),
[medición](g102_common.json), [repetición](g102_restart.json), [cierre](g102_closure.json).

## En palabras fáciles de entender

El terminal volvió a funcionar y pudimos entrenar tres versiones del modelo.
La idea principal era enseñarle a mirar cada palabra junto con sus vecinas.
Esa idea no dio mejores respuestas. La versión que miraba palabras aisladas
sí contestó bien cuatro preguntas más que nuestro modelo anterior, en el
mismo conjunto de prueba. Sin embargo, siguió dando siete respuestas nuevas
equivocadas. Además, algunas respuestas tardaron más de los cinco milisegundos
permitidos. En la panadería volvió a quedarse sin contestar horario y dirección.

Por eso conservamos los modelos y los resultados como experimentos. No hay
una mejora lista para reemplazar la versión estable. Aprendimos que, con estos
datos y esta enseñanza, añadir palabras vecinas no ayuda; repetir más veces
esta misma idea no está justificado por los resultados. La pequeña ganancia
de la otra versión necesita pruebas nuevas antes de considerarse general.

Entre los modelos públicos revisados, Sauerkraut15m sigue siendo el primero
que mediría por su tamaño y porque incluye español. No se descargó ni se probó
en esta tanda; sus resultados publicados no garantizan acierto ni velocidad aquí.

## Comparación completa

Seis negocios de desarrollo ya gastado, 157 turnos, 102 contestables. Juez
automático por claves, sin reserva nueva ni juez independiente. Estas cifras
no se comparan directamente con el 35,9 % histórico del banco G-62 completo.

| Variante | Útiles /102 | Errores nuevos | Elección cruda /61 |
|---|---:|---:|---:|
| Estable | 29 | 0 | 22 como candidata interna, referencia previa |
| Propio G-98 | 32 | 7 | 8, referencia previa |
| G-99 léxico, mínimo 0,4 | 29 | 0 | 19, referencia previa |
| G-102 contexto, mínimos 0,4 y 0,9 | 29 | 0 | 13 |
| G-102 palabras aisladas, mínimo 0,4 | **36** | **7** | 17 |
| G-102 palabras aisladas, mínimo 0,9 | 29 | 0 | 17 |
| G-102 preguntas mezcladas, ambos mínimos | 29 | 0 | 2 |

Principal preregistrado: contexto con mínimo 0,9. Falla utilidad, mejora de
selección y velocidad. La variante secundaria de 36 tampoco alcanza el paso
intermedio de 37 ni la meta de 62; añade errores. Respecto a G-98 gana cinco
respuestas útiles y pierde una: saldo de cuatro, sin prueba de generalidad.

El estable ya tenía 12 citas equivocadas con dato y siete sin dato. G-98 y
G-102 palabras aisladas a 0,4 tienen 16 y diez, respectivamente. Cero errores
**nuevos** no significa cero errores totales. La cantidad de errores coincide
entre estas dos variantes; no se afirma identidad de los casos. No cambió
ninguna respuesta que ya emitía el estable. Citas siempre literales: eso no
garantiza pertinencia. Al conservar respuestas previas, el techo es 90/102.

## Velocidad, repetición y caso del usuario

Una hebra, respuesta completa y dos procesos con distinto orden interno
(`PYTHONHASHSEED=0/1`). p95 es el tiempo no superado por el 95 % de las respuestas.

| Variante | p95 primera / repetición, ms | Máximo primera / repetición, ms |
|---|---:|---:|
| Contexto 0,9, principal | 4,000 / **5,096** | 4,457 / **6,257** |
| Palabras aisladas 0,4 | 3,969 / **5,236** | 4,514 / **8,528** |

También falla el tiempo condicionado a activar el respaldo en la repetición:
contexto p95/máximo 5,251/6,255 ms; palabras aisladas 5,400/8,525 ms.
Se conservan los picos, incluido G-99 léxico de referencia: 11,115/11,502 ms.
Las nueve rutas producen respuestas idénticas tras reinicio. No se repitieron
mediciones para buscar una corrida que pasara el límite.

[Panadería e integración](g102_user_integration.json): base exacta del usuario,
texto completo e historial indicado. Las seis variantes G-102 no contestan
horario ni dirección; citan correctamente «No aceptamos cheques» y se abstienen
sobre estacionamiento. Pierden el horario que G-98 sí lograba citar.
Desactivación, cambio y retirada del documento pasan en las tres arquitecturas.
Motor y base conservan sus huellas. Pruebas finales: **22/22**, 17,585 s.

## Enseñanza y costos

Mismos 6000 SQAC humanos y 1737 ejercicios sintéticos anteriores; seis épocas,
1,314 millones de parámetros con contexto y 1,298 sin vecinos. Comprobación
educativa: 889/1534 contexto, 911 sin vecinos y 558 con preguntas mezcladas;
no son porcentajes de utilidad del kiosco. Se truncaron 1950 unidades de
enseñanza y 318 de comprobación a 64 palabras, sin excluir casos. No es lectura
ilimitada; las preguntas de ambas particiones cabían en 32 palabras.

Calibración separada: 66/455 propuestas correctas para contexto, 81 para
palabras aisladas y 20 mezcladas. Confianzas máximas 0,3864 /0,5079 /0,0455.
La calibración de contexto no admite respuestas nuevas al mínimo 0,4.

Enseñanza y calibración: **987,580 s CPU**, 985,980 s de pared, pico 1,25 GiB.
Total nuevo instrumentado: **al menos 1037,828 s CPU** (enseñanza, dos
evaluaciones, panadería/integración y pruebas finales). Lecturas, pruebas
iniciales y preparación manual no se midieron completamente; corpus, base
y aprendizaje G-97/G-98 reutilizados. Sin GPU ni nuevos pesos descargados.
Código congelado `5ac33d4`; pesos/calibración `fcce235`; no cambios de mínimos.

## Recomendación y fuentes que orientan el siguiente paso

Cerrar esta tanda; no promover ni repetir ciegamente la arquitectura contextual.
Conservar el resultado de 36/102 como ganancia parcial con errores y costo mayor.
[Conv-KNRM](https://boston.lti.cs.cmu.edu/appendices/WSDM2018-ConvKNRM/) motivó la
hipótesis de contexto local; esta adaptación no confirma una mejora para Leobot.
La siguiente comparación externa propuesta sigue siendo
[SauerkrautLM-Multi-ColBERT-15m](https://huggingface.co/VAGOsolutions/SauerkrautLM-Multi-ColBERT-15m),
con [33m](https://huggingface.co/VAGOsolutions/SauerkrautLM-Multi-ColBERT-33m)
como referencia de calidad: ambos incluyen español. Son candidatos pendientes,
sin medición local de cinco milisegundos. [NeuML Femto](https://huggingface.co/NeuML/colbert-muvera-femto)
es más pequeño, pero la evidencia publicada es en inglés. Cualquier nueva
prueba requiere revisión fijada, preregistro y medición completa, fuera del motor.
