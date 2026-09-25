# Auditoría 5.10 de `freeze-G-54r` como candidato a `estable-G-14`

- Fecha: 2026-09-25, de 04:28 a 04:52 (unos 25 min de los 60 disponibles).
- Auditor: subagente nuevo de Claude Code (Opus 5.5), en una copia aislada.
- Encargo: auditor.
- Copias usadas: `git worktree` de `freeze-G-54r`, `freeze-G-54` y `estable-G-13`. Se borraron al terminar.
- No se modificó `leobot/` ni las pruebas. No se hicieron commits ni tags. Un solo proceso pesado a la vez, siempre con `timeout` y con al menos 4 GB libres antes de cada uno.
- Huellas comprobadas:
  - `freeze-G-54r:leobot` = `5c6f2d59367562c14b5d9158f9ef1532d8fa5f25`
  - `freeze-G-54:leobot` = `0d5eda1ec8f88d8e96ad1f8aeefcc76f05e73acb`
  - `estable-G-13:leobot` = `0066ff79b18df6dbdb40dcdb82684b5c4bf27a1a`

## Cifras: guardadas frente a reproducidas

| Qué | Guardado | Reproducido por el auditor |
|---|---|---|
| SHA-256 de la base (`base_educada`, desde `freeze-G-54r`) | `67905a5ec2c14838…` | `67905a5ec2c14838b53e1d43566c4cc51cbd65589359735c99896cbb8490e27b`: **idéntica**. 95,2 MiB, 134,9 s de CPU, 443 MiB de RAM residente. No hizo falta quitar el límite de 100 MiB. |
| Reserva cuádruple, `freeze-G-54r` | 96/127 (igual que `estable-G-13`) | **96/127**, 2 afirmaciones falsas, 1 abierta equivocada |
| Referencias, `freeze-G-54r` | 30/48 | **30/48**, 0 falsas, 1 equivocada |
| Charla, `freeze-G-54r` | 31/64 | **31/64**, 0 falsas, 2 equivocadas |
| `answer_voice=False` en `freeze-G-54r` | mismos aciertos | 96, 30 y 31. **Ninguna pregunta cambia de acierto a fallo ni al revés.** Cambia el texto en 72, 27 y 46 respuestas. |
| `estable-G-13` sobre los mismos conjuntos, corrido por el auditor con la misma base | 96 / 30 / 31 | **96 / 30 / 31**. El texto es idéntico al de `freeze-G-54r` sin voz en 127/127, 48/48 y 64/64 respuestas. |
| `freeze-G-54r` con `PYTHONHASHSEED=1` | — | Respuestas idénticas a las de semilla 0 en las 239, con voz y sin voz |
| p95 de la charla, `freeze-G-54r` | 108 ms (`freeze-G-54`) | 98,9 ms (con voz) y 97,7 ms (sin voz); dentro de 200 ms |
| Paso 5: `experiments.g54_conversacion` en `freeze-G-54` sobre `referencias_g54_doble.tsv` | `results_v3/g54_referencias_g54_doble_hashseed0.json` | **Las 22 claves son idénticas, salvo los tiempos**: tratamiento 30, cada ablación 30, sin el contenido de G-54 30, sin G-52 28, sin G-53 31, sin memoria y memoria barajada 7, renombrado 48/48, reinicio 48/48 |
| Juicio de naturalidad | 3,08 / 1,89 / 4,63; errores gramaticales 1 / 1 / 0 | Recalculado con `g54_naturalidad puntuar` desde `scratchpad/g54/juez_mapa.json` y `juez_juicio.json`: **3,078 / 1,891 / 4,625; 1 / 1 / 0** |
| Textos juzgados frente a `freeze-G-54r` | — | 63 de 64 idénticos. El que difiere es el «sí» falso de `scoped_polarity` («¿Fue mi papá al almuerzo?»). En `freeze-G-54r` la respuesta es «No, me contaste que tu papá no fue…», que es la correcta. |

Las huellas SHA-256 de los tres conjuntos (`8f51a9b2…`, `33a92ba8…` y `ba24aec2…`) coinciden con las anotadas en los JSON de resultados.

## Hardcodeo (5.7)

**Diff `estable-G-13..freeze-G-54r -- leobot`** (dialogue.py, reading.py y syntax.py).
- No hay ramas que dependan del nombre de un conjunto o del contenido de una pregunta.
- No hay tablas de pregunta y respuesta, ni listas de palabras de contenido.
- Todo lo demás son etiquetas y rasgos de UD (`nsubj`, `cop`, `aux`, `Person=1`, `Number[psor]=Plur`…) y claves internas.
- La tabla de formas sale de contar AnCora `train` y COSER `train` (`experiments/base_educada.py`, solo con `observe_forms`).

**Palabras propias de la voz.** Están en `leobot/reading.py:598-607` y en `leobot/dialogue.py:862`. Hay tres diferencias con lo declarado:
1. `leobot/reading.py:600`: `'No, me contaste lo contrario.'`. La expresión «lo contrario» **no figura en ninguna lista declarada**: ni en el preregistro (línea 66), ni en la enmienda (línea 166), ni en el docstring (`reading.py:591`), ni en la lista del encargo.
2. `leobot/reading.py:607`: `'No lo sé: eso no me lo has contado.'`.
   - Añade «eso», que no está declarado.
   - El preregistro (línea 66) declara «no me lo contaste», no «no me lo has contado». La forma del código sí está en el docstring y en la lista del encargo.
3. `leobot/reading.py:604`: «pero también que» figura en la lista del encargo, pero **no en el preregistro ni en el docstring** (`reading.py:591-593`, que nombra solo cinco expresiones).

Las tres son palabras de la voz de quien responde, no conocimiento del dominio. No cambian ningún acierto (con voz y sin voz dan lo mismo). **Es una falta en lo declarado, no hardcodeo que resuelva preguntas.** Conviene declararlas en el estado.

**Otras cosas escritas a mano que no son palabras**, anotadas para que conste:
- `reading.py:585-586`: una expresión regular que ajusta los espacios junto a los signos de puntuación (`, . ; : ! ? ) »` y `( « ¿ ¡`). Es ortografía, no una construcción.
- `syntax.py:236` y `reading.py:507, 530 y 533`: las reglas de terminación se agrupan por las dos últimas letras del lema. Está declarado («según la terminación del lema»).
- `reading.py:41`, `FORM_SUPPORT = 3`: declarado en el punto 7 de la enmienda.
- `syntax.py:33`, `FORM_RULE_SUPPORT = 2`: umbral de lemas distintos por regla. **No está en el preregistro.** Es menor.
- `reading.py:524`: las personas del plural no se vuelven a decir. Está declarado en el punto 6 de la enmienda.

**Diff `estable-G-13..freeze-G-54 -- leobot`** (el contenido retirado: entities.py, reference.py y reading.py).
- Solo usa etiquetas y rasgos de UD e interruptores.
- Las palabras en español aparecen solo en comentarios y docstrings, como ejemplos.
- No hay hardcodeo.

**Pruebas.**
- Entre `estable-G-13` y `freeze-G-54r` no se borró ni se cambió ninguna prueba existente. Solo se añadió `tests/test_g54_conversation.py`.
- Ninguna prueba anterior fija los textos antiguos.

**Código de la voz.** Las funciones de la voz son idénticas en `freeze-G-54` y `freeze-G-54r` (comparado por AST): `_swapped_form`, `_restated`, `_written`, `_voiced`, `observe_forms`, `_count_forms` y `_compile_forms`. Solo cambia cómo se le pasan las frases de apoyo: por `source` (`reading.py:422`) en lugar de por posición. En la conversación, `source` es único por oración (`reading.py:150`), así que el resultado es el mismo.

## Procedimiento

| Paso | Commit o tag y hora | Veredicto |
|---|---|---|
| Preregistro | `157a4f7`, 24-09 23:24 | Antes de cualquier cambio en el motor. `estable-G-13` tiene el mismo árbol que `freeze-G-53r` (`0066ff79`). El primer cambio del motor es `f16bf9b`. |
| Enmienda | `e67fea9`, 25-09 00:50:40, padre de `f16bf9b` | **Precede al tag `freeze-G-54`** (tag creado a las 00:52:26 sobre `2f03a66`; mensaje «enmienda e67fea9»). Árbol `0d5eda1e` = `f16bf9b:leobot`. |
| Conjuntos | borradores en `scratchpad/g54/*.tsv` con fecha de 00:54:11 a 00:56:20; validadas de 00:57:29 a 00:59:27; commit `50a5c1e` a las 00:59:38 | **Escritos después del tag y en git antes de los resultados** (`dfe8a0a`, 01:38:56). |
| Encargos a los redactores | `scratchpad/g54/prompt_*.txt` | Coinciden con el encargo registrado (`experiments/g54_encargo_charla.md`, en `157a4f7`). No contienen ejemplos del usuario (se buscó «Luz», «mamá», «papá» y «almuerzo»: 0 apariciones). Las cabeceras anotan modelo, fecha y encargo. |
| Retirada 5.9 del contenido | JSON de los tres conjuntos | **Bien aplicada.** Siete de las ocho ablaciones sueltas dan cifras idénticas al tratamiento: aporte 0, mismas afirmaciones falsas, mismas abiertas equivocadas y mismos errores confiados. `scoped_polarity` aporta −1 y suma 1 afirmación falsa. Ninguna reduce las falsas ni las equivocadas, así que las ocho cumplen la regla de la línea 124. |
| G-52 | sin G-52: 152 frente a 156 | Aporta +4; bien conservado según la regla de la enmienda. |
| `freeze-G-54r` | `7dcae1c`, tag a las 01:48:44 | Es `estable-G-13` más la voz: sin voz, su texto es idéntico al de `estable-G-13` en las 239 respuestas. |

## Salvedades

1. **Palabras de la voz sin declarar:** «lo contrario» (`reading.py:600`) y «eso» (`reading.py:607`). Además, «no me lo has contado» y «pero también que» no coinciden con el preregistro. Hay que declararlas en el estado; no afectan a las cifras.
2. **La enmienda y el código se guardaron en el mismo segundo** (00:50:40). La enmienda se escribió después de programar, como ella misma dice, e incluye las cifras de desarrollo. Precede al tag y al material nuevo, pero no al código. Es la misma salvedad que se registró en G-53.
3. **Los datos del juicio de naturalidad no están en git.** Solo se guardó el resumen (`results_v3/g54_naturalidad.json`, en `5dfaa9b`, después del tag). Los ítems, el mapa y el juicio siguen en el scratchpad. Además, se juzgaron respuestas de `freeze-G-54` y no de `freeze-G-54r`: 63 de 64 son idénticas y la distinta mejora en `freeze-G-54r`.
4. **La base de la comparación con `estable-G-13`** es la de `freeze-G-54r` (`67905a5e`), que trae tablas de formas que `estable-G-13` no usa. No es la base que `estable-G-13` construiría por sí mismo. Las corridas de `estable-G-13` que dejó la sesión (`scratchpad/g54/g13_*.json`) no anotan huella ni base, pero dan el mismo texto.
5. **Posible costo de latencia** en `reading.py:422`: `rows_of` recorre toda `reading_utterances` y reconstruye `set(sources)` en cada fila, en cada respuesta de sí o no. Con una memoria grande podría crecer. La sesión anotó +17,8 % en español, cerca del tope del 20 %. El auditor no lo verificó.
6. **«No lo sé: eso no me lo has contado.»** (`dialogue.py:862`) se aplica también cuando lo preguntado venía de un documento leído, no de algo contado. Es un asunto de naturalidad, no de aciertos.
7. El mensaje del commit `50a5c1e` dice «charla 65», pero el conjunto tiene 64 preguntas calificadas (32 + 32). Es una errata.
8. **No se hizo:**
   - la regresión completa, la latencia, el tablero AGI, la sonda de lectura y SQuAD-es 2400, que no estaban en el encargo;
   - el paso 5 sobre la reserva y la charla: solo se repitió sobre las referencias.

## Veredicto

**Confirma** que `freeze-G-54r` puede promoverse a `estable-G-14`, con las salvedades de arriba (sobre todo la 1 y la 3, que deben quedar registradas).

La base es idéntica byte a byte. Las cifras del motor promovido se reproducen exactas (96/127, 30/48 y 31/64). Son iguales a las de `estable-G-13`, que el auditor corrió también, y apagar la voz no cambia ningún acierto. No depende de `PYTHONHASHSEED`. El experimento de `freeze-G-54` se reproduce exacto en las referencias. La retirada del contenido sigue la regla preregistrada. No hay hardcodeo que resuelva preguntas.

## En palabras fáciles de entender

Revisamos si la versión nueva de Leobot se puede guardar como versión buena. Esa versión solo cambia la forma de contestar: en lugar de «Sí, según lo que me dijeron», ahora dice «Sí, me contaste que te mudaste hace dos semanas». Repetimos sus exámenes desde cero, con los mismos datos, y salieron exactamente las mismas notas que se habían anotado: 96 de 127, 30 de 48 y 31 de 64. Son las mismas notas que la versión anterior. La nueva forma de hablar no le hizo ganar ni perder ninguna respuesta; solo suena más natural. Un juez que no sabía quién contestaba le dio 3,1 sobre 5, frente a 1,9 de la forma antigua. También comprobamos que los exámenes se escribieron después de cerrar el programa, que nadie le escondió respuestas y que las mejoras que no funcionaron se quitaron según la regla acordada de antemano. Encontramos tres detalles menores. Leobot usa un par de palabras propias («lo contrario» y «eso») que no se habían anotado de antemano. Las hojas del juez no quedaron guardadas en el historial. Y una parte nueva del programa podría volverlo algo más lento cuando tenga mucha memoria. Nada de eso cambia las notas. Nuestra conclusión: la versión se puede aprobar, dejando anotados esos detalles.
