# G-43b — retirar la clase de respuesta y conservar lo que aportó

Fecha: 2026-09-24. Preregistro previo al código. Base: `freeze-G-43` (árbol `44c668c5`).

## Fallo medido

En su [reserva](../results_v3/g43_reserva_hashseed0.json), G-43 sacó 26/30 (G-42: 24; subagente: 30) y pasó todo salvo un criterio: el aporte de la clase de respuesta, que fue +0,0008 F1 en la [MLQA no vista](../results_v3/g43_mlqa_reserva.json) y 0 en conversación. Con el desempate por el lector de G-28, la clase queda redundante. La regla 5.9 manda descartar lo que cuesta sin ventaja.

## Cambio

- **Se retira la clase de respuesta:** qué se guarda de cada ejemplo, la compilación, el costo por clase y la clase de palabra fuera de contexto. La puntuación queda: cobertura, espejo (palabras de contenido), preposición y función. El lector de G-28 desempata.
- Se conserva todo lo demás de G-42 y G-43: interrogativas por posición, una sola vía de abstención, alineación estructural con subárboles máximos, coordinados colgados de la cabeza común, distancias en palabras de contenido, alineación por raíz, y sí/no por estructura sin afirmar lo subordinado.
- Las pruebas focales de la clase se retiran con el mecanismo. Las de coordinados y verificación se conservan.
- **Qué se elimina:** el código de la clase de respuesta.

## Evaluación

La receta de la base educada es la misma. Hay una **reserva nueva** de conversación después de `freeze-G-43b`, con el mismo procedimiento (redactor, validador, subagente sin claves), y una **muestra MLQA no vista** con la semilla de `freeze-G-43b`, sacada entre los casos no usados en educación, en desarrollo ni en la muestra de G-43.

Líneas base en la reserva:
- G-42 congelado;
- G-43 congelado;
- la estrategia «siempre no lo sé»;
- el subagente.

Controles:
- ablación de la verificación estructural;
- ablación de la alineación;
- sin memoria;
- barajada;
- renombrado.

## Puerta (candidata a `estable-G-11`)

| Criterio | Umbral |
|---|---|
| Aciertos en la reserva | ≥ 60 % y ≥ G-42 congelado + 2 |
| No inferior a G-43 congelado | ≥ G-43 − 1 |
| Sí o no falsos (sin abstenciones) | ≤ 1 |
| Respuestas abiertas equivocadas | ≤ 3 |
| Memoria barajada | 0 aciertos en abiertas y sí/no |
| Renombrado: respuestas invariantes | ≥ 90 % |
| MLQA no vista, bot educado completo | F1 ≥ lector de G-28 solo − 0,005 |
| Regresión completa | sin fallos nuevos |
| Latencia fija intercalada con `estable-G-10` | p95 sin empeorar más de 20 % y dentro de los presupuestos absolutos |
| Respuesta en conversación | p95 ≤ 200 ms |
| Verificación independiente 5.10 | cifras reproducidas, sin hardcodeo ni filtraciones |

Si pasa, se crea `estable-G-11` y se actualizan el tablero y la latencia. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

En el último intento, Leobot aprendió qué tipo de palabra responde a cada pregunta («cuántos» con un número), pero eso no mejoró nada. Otra pieza, la que desempata con lo aprendido al leer, ya hacía ese trabajo. Por eso se quita, y se queda lo que sí sirvió: revisar quién hace qué antes de decir «sí» y no dar por hecho lo que alguien solo dijo. Después se prueba con preguntas nuevas y, si pasa, esta versión queda como la nueva versión estable.
