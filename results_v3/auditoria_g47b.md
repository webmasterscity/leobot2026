# Auditoría independiente 5.10: G-47b / candidata `estable-G-12` (2026-09-24)

Auditor: subagente Claude (Opus 5.5), en una copia aislada con `freeze-G-47b` (árbol `20a694f4…`, igual a `main:leobot`). No toqué `leobot/` ni las pruebas, y no hice commits. Guardé los scripts y las salidas en `scratchpad/aud47b/`.

## 1. La base se reproduce igual
- Reconstruí la base con `PYTHONHASHSEED=0 python3 -m experiments.base_educada corpus_ud …`: 59 s de CPU y 399 MiB de RSS.
- SHA-256 `7b58760648d76c36…`, **idéntico byte a byte** a `base_freeze_g47b.json`. `base_g47b_dev.json` (12:18, antes de congelar) también es idéntico.

## 2. Conversación: cifras reproducidas frente a guardadas (hashseed 0)
| Variante | Reserva doble (64) guardada / mía | Referencias (24) guardada / mía |
|---|---|---|
| tratamiento | 39 / 39 (1 falsa, 3 abiertas mal, «no» 3/13) | 10 / 10 (0 falsas, 1 abierta mal) |
| sin `lemma_sets` | 39 / 39 | 9 / 9 |
| sin `g47b_structure` | 39 / 39 | 10 / 10 |
| ambas ablaciones | 39 / 39 | 9 / 9 |
| sin memoria · barajada | 16 · 16 / 16 · 16 | 3 · 3 / 3 · 3 |
| renombrado (invariancia) | 60/64 / 60/64 | 23/24 / 23/24 |
| `estable-G-11` (árbol `b9038ee5`, base `af18f511`) | 36 / 36 | 7 / 7 |
| G-47 congelado (árbol `43dcbddd`, base `11df8a2a`) | 39 / 39 | 9 / 9 |

- **0 campos distintos** en todo el JSON, incluido el desglose por tipo. Solo cambian los tiempos. Mi p95 de conversación fue 51 y 43 ms (guardado: 48 y 37), por debajo de 200 ms.
- Con `PYTHONHASHSEED=1`, el tratamiento da los mismos aciertos: 39/64 y 10/24.
- La SHA de los conjuntos coincide con la guardada: `6ca7150e…` y `291e68d4…`. La semilla de SQuAD-es es 547788020 = `0x20a694f4`, correcta. No re-ejecuté la lectura SQuAD-es porque no estaba en el encargo.
- La evaluación de la puerta guardada es correcta:
  - pasan: aciertos (39 ≥ 39), afirmaciones falsas, abiertas mal, barajada y renombrado;
  - fallan: aporte (0 < +2), claves «no» (3/13) y referencias (10 < 12).

## 3. Hardcodeo (5.7), `git diff freeze-G-46b freeze-G-47b -- leobot`
- No hay ramas según el nombre de un banco de pruebas ni según el contenido de las preguntas. Tampoco hay tablas de pregunta y respuesta.
- El motor no importa ni lee `experiments/`, `tests/`, `results_v3` ni archivos externos.
- Todos los textos literales nuevos son etiquetas del esquema UD («nsubj», «NOUN», «Gender=Fem»…) o claves internas. Hay dos excepciones.
- Lo del español se aprende de los datos, y lo comprobé en la base:
  - `lemma_sets` (261 formas; «llamado» → {llamado, llamar}), `morph_table` (6707), `morph_endings` (456), `impersonal` (= [«haber»]) y `split_table` («del» = de+el) salen de AnCora `train`;
  - `answer_classes` (318) sale de los 2000 ejemplos MLQA.
- **Salvedad menor:** hay dos palabras españolas escritas a mano en `leobot/reference.py`, de G-47 y declaradas en su enmienda:
  - `'a'` (l. 177), para detectar el doblado «le … a Julián»;
  - `'de'` (l. 315), que se inserta al reescribir un posesivo («su perro» → «perro de X»).
  - Son gramática general, no respuestas, y podrían aprenderse: la preposición más frecuente de `nmod` en AnCora. Conviene registrarlas como conocimiento programado.

## 4. Filtraciones del conjunto reservado (held-out)
- Busqué las 166 frases y los 603 grupos de 4 palabras seguidas (4-gramas) de `reserva_g47b_*` y `referencias_g47b_validada.tsv`:
  - **en `leobot/` y `experiments/`: 0 coincidencias;**
  - en `tests/` y `prereg/`: solo 4-gramas genéricos («de qué color es», «el hermano de Marta») y la frase «¿Cuántos hijos tiene Marta?», ya presente en G-42 (anterior). Son coincidencias de redacción, en archivos que el motor no lee.
- Base: 0 frases y 7 4-gramas genéricos («cómo se llama el», «en qué año empezó»).
- Además, la base es idéntica a una construida a las 12:18, antes del tag y de los conjuntos. **No puede contenerlos.**

## 5. Orden de los preregistros
- G-47: preregistro `769b818` (10:02) → código y enmienda `13607f8` (11:50) = `freeze-G-47` → conjuntos desde las 11:54.
- G-47b: preregistro `b9667ff` (12:14) → código y enmienda `ce27e8f` (12:48:38) = `freeze-G-47b` → conjuntos desde las 12:51:03 → resultados `43c91bf` (13:06).
- Los preregistros preceden al código. En `tests/` solo hay archivos añadidos: no se modificó ninguna prueba.
- **Salvedades:**
  - Cada enmienda va en el mismo commit que el código. Git prueba que precede al tag y a los conjuntos, no que preceda al código. La puerta no cambió.
  - Los tags son ligeros, sin fecha propia.
  - Los conjuntos reservados están fuera de git: solo quedan su SHA de 16 caracteres y la fecha de los archivos en `/tmp`. Es la práctica adoptada con el usuario, pero se aparta de 5.10 («se hace commit antes de ejecutar»), y si se borra `/tmp` no se podrá volver a auditar.

## 6. Controles y defectos del evaluador
- No encontré defectos que cambien una conclusión.
- `afirma_falso` no cuenta una respuesta inventada cuando la clave es «no lo sé», pero aquí «no lo sé» acertó 14/14 y 3/3, así que no hay efecto.
- El renombrado mide invariancia, como dice el preregistro.
- No se aplicaron ni se justificaron en el preregistro los controles de contraevidencia, reinicio a mitad de la conversación y señal confundida (5.4).
- **Observación para la promoción (5.9):**
  - En desarrollo, lo propio de G-47b sumó +18 (408 frente a 390). En el conjunto reservado sumó **0** en la reserva doble y **+1** en referencias.
  - La ventaja reproducida sobre `estable-G-11` (+3 y +3) viene de G-47, que obtiene lo mismo: 39 y 9.
  - Por eso, promover `freeze-G-47b` en lugar de `freeze-G-47` necesita una justificación registrada: +1 en referencias, sin regresión y latencia igual.
  - En los conjuntos de G-47, que fueron desarrollo para G-47b, `freeze-G-47b` saca 44/65 y 16/24. No cuentan como reservados.

## Veredicto
- **Reproduce:** sí, exactamente (base, tratamiento, ablaciones, controles y líneas de comparación).
- **Hardcodeo:** no; solo dos preposiciones escritas a mano («a», «de»), que son menores.
- **Filtraciones:** no.
- **Preregistro antes que el código:** sí, con las salvedades de enmienda en el mismo commit y conjuntos fuera de git.
- **Puerta de G-47b:** no superada, como se registró.

## En palabras fáciles de entender
Repetí por mi cuenta todas las pruebas de esta versión de Leobot y salieron exactamente las mismas cifras. No encontré trampas: no tiene respuestas escondidas, y lo que sabe del español lo aprendió leyendo textos, salvo dos palabras pequeñas («a» y «de») que alguien escribió a mano. Tampoco vio de antemano las preguntas del examen. Esta versión contesta mejor que la versión oficial anterior, pero esa mejora viene del paso anterior (G-47); los arreglos de este paso no ayudaron en el examen nuevo. Antes de declarar esta versión como oficial, conviene explicar por escrito por qué se conservan esos arreglos.
