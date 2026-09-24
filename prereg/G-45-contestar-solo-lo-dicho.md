# G-45 — contestar solo lo que está dicho

Fecha: 2026-09-24. Preregistro previo al código. Base: `freeze-G-44b` (árbol `7f81d4ab`).

## Fallo medido

En la [reserva doble de G-44b](../results_v3/g44b_reserva_hashseed0.json) (40/61; subagente 60/61), 5 fallos son respuestas a lo que nadie dijo. Con el motor de G-44b sobre los 7 conjuntos de conversación ya gastados (247 preguntas), el acierto por vía de respuesta es:

| Vía | Preguntas | Aciertos | Clave «no lo sé» |
|---|---|---|---|
| alineación estructural | 121 | 109 | 3 |
| lector de G-28 sobre lo dicho en conversación | 41 | 10 | 18 |
| verificación de sí/no (sí, no, dicho por otro) | 31 | 31 | 0 |
| «No lo sé» | 54 | 28 | 24 |

Causas:
1. **El lector de G-28 presupone que la pregunta tiene respuesta.** Se educó con MLQA, donde cada pregunta se escribió sobre su párrafo. Cuando ninguna oración recordada cubre la pregunta, igual elige un tramo. Sobre un documento leído esa presuposición es razonable. Sobre lo dicho en conversación no lo es: allí se pregunta también lo que nadie dijo, y «no lo sé» es la respuesta normal.
2. **Un sustantivo distinto no contesta.** «¿Cuántos caballos hay en la finca?» → «cuarenta vacas»; «¿De qué color es el carro de Tomás?» → «el mes pasado». Si el sustantivo de la pregunta («caballos») no está en la oración, una candidata encabezada por otro sustantivo común («vacas») habla de otra cosa. La excepción son los sustantivos de categoría, como «color» o «tipo», cuya respuesta casi nunca los repite.

## Cambio (5.8)

1. **El lector de G-28 solo sobre documentos leídos.** Cuando ninguna oración cubre la pregunta, el lector de G-28 busca solo entre lo leído en documentos, no entre lo dicho en conversación (la fuente de G-41, `conversación:`). Si no hay documento que lo cubra: «No lo sé». Interruptor: `conversation_guessing` (apagado por defecto; encendido para la ablación).
2. **Choque de sustantivos en la alineación.** Si la pregunta tiene un sustantivo tras la interrogativa y la oración no lo contiene, no es candidata una que esté encabezada por un sustantivo común de otro lema. La excepción son los **sustantivos de categoría**, que se aprenden de la educación: cada ejemplo de lectura guarda el principio de la pregunta (6 palabras) y qué palabras de ese principio aparecen en la oración que responde. Al consolidar, un sustantivo tras una interrogativa es de categoría si falta en la oración que responde en al menos la mitad de sus ejemplos, con al menos 5 ejemplos. Interruptor: `noun_clash`.
3. **Evaluador:** el renombrado usa una lista de nombres suficiente y sin cifras. En G-44b, 27 nombres sustitutos llevaban cifras y el etiquetador los trató como números.

5.8:
- **Qué fallo resuelve:** las respuestas a lo no dicho.
- **Por qué no bastan los actuales:** el lector de G-28 no tiene noción de pregunta sin respuesta, y la alineación acepta cualquier sustantivo.
- **Qué lo distingue:** la ablación con los dos interruptores; MLQA no vista, donde el punto 1 no debe cambiar nada porque todo es documento leído.
- **Qué se elimina:** las adivinanzas del lector de G-28 sobre lo dicho en conversación.

**Enmienda antes de congelar (2026-09-24), por lo visto en desarrollo.**
- **Error de nombre de variable.** Al guardar la presencia de las palabras de la pregunta se reutilizó el nombre de variable que el lector de G-28 usa como ámbito de sus estadísticas. El modelo de lectura se corrompió (de 5,4 a 20,6 MB) y la base superó el límite de carga. Se corrigió antes de medir.
- **Abstención sin «No lo sé».** Cuando el lector de G-28 no encuentra oración, se abstiene con «No encuentro en lo que leí…». Eso incumple la regla de una sola abstención de G-42 (punto 2) y ya ocurría desde entonces. Con el punto 1, la mayoría de las preguntas sin respuesta pasan por ahí. Ahora, con interrogativas aprendidas, esa abstención es «No lo sé: …».

Medido en desarrollo después de la corrección (7 conjuntos gastados, 247 preguntas; MLQA visible):

| Variante | Conversación | MLQA F1 |
|---|---|---|
| G-45 | 187 | 0,2252 |
| solo el lector sobre documentos | 186 | 0,2252 |
| solo el choque de sustantivos | 178 | 0,2252 |
| ablación (ambos interruptores con el comportamiento de G-44b, con la abstención corregida) | 178 | 0,2252 |

La puerta no cambia.

## Evaluación

- **Desarrollo:** los 7 conjuntos de conversación gastados (247 preguntas) y MLQA visible.
- **Reserva doble nueva** después de `freeze-G-45`. Se miden G-45, G-44b congelado, «siempre no lo sé», el subagente, la ablación, sin memoria, barajada y renombrado.
- **MLQA:** 600 casos no vistos con la semilla de `freeze-G-45`, excluidas todas las muestras anteriores.

## Puerta

| Criterio | Umbral |
|---|---|
| Aciertos en la reserva doble | ≥ 65 % y ≥ G-44b congelado + 3 |
| Aporte (G-45 − ablación con ambos interruptores en el comportamiento de G-44b) | ≥ +3 |
| Sí o no falsos (sin abstenciones) | ≤ 2 |
| Respuestas abiertas equivocadas | ≤ 15 % de las preguntas abiertas |
| Memoria barajada | 0 aciertos en abiertas y sí/no |
| Renombrado: respuestas invariantes (evaluador corregido) | ≥ 90 % |
| MLQA no vista (600) | F1 ≥ lector de G-28 solo − 0,005 |
| Regresión completa | sin fallos nuevos |
| Latencia fija intercalada con `estable-G-10` | ≤ +20 % y dentro de presupuestos |
| Respuesta en conversación | p95 ≤ 200 ms |
| Verificación independiente 5.10 | cifras reproducidas, sin hardcodeo ni filtraciones |

Si pasa, `estable-G-11`. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Cuando nadie le había dicho algo, Leobot a veces igual respondía algo, porque aprendió a leer con exámenes donde cada pregunta siempre tenía respuesta en el texto. Ahora distinguirá: si le preguntan por un documento que leyó, puede buscar la mejor respuesta como en esos exámenes; si le preguntan por algo que le contaron en la conversación y nadie lo dijo, dirá «no lo sé». Y si le preguntan cuántos caballos hay y solo le hablaron de vacas, no contestará con las vacas.
