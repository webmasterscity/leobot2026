# G-41 — lo dicho en conversación se recuerda y se verifica como lo leído

Fecha: 2026-09-24. Preregistro previo al código. Base: `freeze-G-39d` (`8355569d`); `estable-G-10` para las comparaciones.

## Fallo medido

En la [validación común](../results_v3/validacion_comun_2026-09-24.json) (conjunto nuevo, redactado por un subagente que no vio el código): Leobot **0/30**, subagente Sonnet 5 **30/30**. Las 30 respuestas de Leobot son «No sé interpretar esa formulación».

## Causas, halladas en el código

1. **Lo dicho en conversación no entra en la memoria literal.** Solo `ingest_document_text` llama a `remember_utterances`. «Ana vive en Lima», dicho en conversación, queda como evidencia cruda de relación y la lectura de G-28 no puede usarlo. Una persona recuerda lo que le dijeron.
2. **Las preguntas de sí o no se contestan con un tramo.** Es un defecto de honestidad ya registrado en G-28.
3. **Abstención sin distinguir.** Leobot responde «No sé interpretar» tanto cuando no entendió como cuando entendió pero le falta el dato. Solo lo segundo es «no lo sé».
4. **Listas escritas a mano.** Las palabras interrogativas (`_question_like`) y la negación («no» en `observe_raw_negative_relation`) están fijadas a mano. La educación sintáctica ya trae ambas anotadas en AnCora (`PronType=Int`, `Polarity=Neg`), pero el motor no las aprende.

## Cambio (5.8)

1. **Memoria de la conversación.** Toda afirmación (lo que no es pregunta) procesada por `respond` se guarda también en la memoria literal (`remember_utterances`) con fuente `conversación`. No se agrega ningún mecanismo nuevo: la conversación usa la misma memoria y la misma lectura que los documentos.
2. **Léxicos aprendidos de la educación sintáctica.**
   - `observe_parsed_sentence` acepta los rasgos morfológicos.
   - Se aprenden las palabras de polaridad negativa y las interrogativas con el criterio de G-35: al menos 3 apoyos y al menos el 90 % de sus apariciones con el rasgo.
   - Sin educación sintáctica, se conserva el comportamiento actual.
3. **Preguntas que ninguna construcción interpreta.**
   - **Abierta** (contiene una interrogativa aprendida o un marcador de hueco aprendido): la lectura existente (`answer_from_utterances`). Si no hay respuesta: «No lo sé».
   - **De sí o no** (sin interrogativa): verificación literal.
     - Si una oración recordada contiene todas las raíces de contenido de la pregunta (sin las palabras de polaridad aprendidas) con la misma polaridad: «Sí».
     - Si la polaridad es la contraria: «No».
     - Si ninguna oración las contiene: «No lo sé».
     - Si hay apoyos de ambas polaridades: «No lo sé» con aviso de contradicción.
4. **«No sé interpretar…»** queda solo para lo que no es pregunta y no se entiende.

5.8:
- **Qué fallo resuelve:** la conversación en español corriente.
- **Por qué no bastan los actuales:** la causa 1 se ve en el código.
- **Qué lo distingue:**
  - la ablación sin memoria de conversación;
  - el control de memoria barajada (lo dicho en otra conversación);
  - el control de renombrado de nombres propios.
- **Qué se elimina:** las listas escritas a mano de interrogativas y de negación, cuando hay educación sintáctica.

## Evaluación

**Bots:**
- **Base educada** ([constructor](../experiments/base_educada.py)): sintaxis con AnCora `train` y lectura con los 2000 ejemplos MLQA de G-28b. No usa nada de ningún conjunto de validación.
- **Línea base:** se mide **antes de congelar** con el motor de `estable-G-10` y su base educada, en el conjunto de desarrollo.

**Desarrollo:** un conjunto nuevo redactado por un subagente independiente con el [encargo fijo](../experiments/validacion_comun_encargo.md) y validado por otro. Se guarda fuera del repositorio y queda visible para el desarrollo.

**Reserva:** después de `freeze-G-41`, un conjunto **nuevo** con el mismo procedimiento, que no se mira antes de ejecutar.

**Controles en la reserva:**
- **Sin memoria de conversación**, con el mismo motor y la misma base.
- **Memoria barajada:** cada conversación recibe las afirmaciones de otra.
- **Nombres renombrados:** una sustitución coherente de los nombres propios del conjunto, hecha por el evaluador.
- **Subagente Sonnet 5**, con el mismo conjunto exportado sin claves.

## Puerta

| Criterio | Umbral |
|---|---|
| Aciertos de Leobot educado en la reserva | ≥ línea base educada + 8 (de ~30) |
| Sí o no erróneos (afirmar lo falso) | ≤ 1 |
| Memoria barajada | 0 aciertos en preguntas abiertas y de sí o no |
| Nombres renombrados | ±2 del tratamiento |
| Sin memoria de conversación | ≤ línea base + 1 |
| Lectura MLQA en desarrollo limpio (G-28b) | F1 sin bajar más de 0,005 |
| Regresión completa | sin fallos nuevos |
| Latencia fija intercalada | ≤ +20 % |
| Respuesta en conversación | p95 ≤ 200 ms |

Se informa la brecha con el subagente sin maquillarla. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Hoy, si alguien le cuenta a Leobot «Ana vive en Lima», no lo recuerda como frase, y luego no puede contestar dónde vive Ana. Ahora recordará lo que se le dice igual que lo que lee. A las preguntas de sí o no contestará sí, no o «no lo sé», según lo que se le haya dicho. Y aprenderá qué palabras preguntan y cuáles niegan a partir de ejemplos, no de una lista escrita a mano.
