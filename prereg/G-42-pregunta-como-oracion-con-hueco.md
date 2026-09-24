# G-42 — la pregunta es una oración con un hueco

Fecha: 2026-09-24. Preregistro previo al código. Base: `freeze-G-41` (árbol `ad568f85`). Segundo diseño de conversación en la fase G.

## Fallo medido

En la [reserva de G-41](../results_v3/g41_reserva_hashseed0.json), Leobot congelado sacó **14/33** y el subagente **32/33**. Los 19 fallos se deben a cuatro causas, halladas en el código y en los datos de educación:

1. **Interrogativas no aprendidas (6 fallos).** G-41 aprende las interrogativas solo de los rasgos de AnCora. «cuántos» tiene 2 apoyos y «cuántas» 1, por debajo del mínimo de 3. «cómo» está anotado como `PronType=Ind` en sus 80 apariciones. Así, «¿Cuántos hijos tiene Marta?» se trató como pregunta de sí o no y recibió «No lo sé».
2. **La consulta estructurada tapa la memoria (3 fallos).** Cuando una construcción convierte la pregunta en consulta formal y el conocimiento formal no tiene el dato, `answer_atom` contesta «No tengo información suficiente…» sin mirar lo que se le dijo en la conversación.
3. **Tramo elegido sin estructura (6 fallos).** El elegidor de tramos de G-28 usa estadísticas de MLQA sobre palabras vecinas. En frases cortas elige mal: «¿De qué color es la bicicleta de Laura?» → «Laura»; «¿Qué enseña Sofía?» → «San José».
4. **Un «no» porque se conoce otro valor en la misma casilla (5 fallos).** Ejemplo: «Andrés trabaja en un banco» → «¿trabaja en un hospital?» → «no». Para eso hace falta saber qué casillas admiten un solo valor y qué formas de decir equivalen («hay un sofá en la sala» = «el sofá está en la sala»). **Queda fuera de G-42.** Será el diseño siguiente.

## Cambio (5.8)

### 1. Interrogativas aprendidas por su posición en las preguntas

Durante la educación se cuenta la primera palabra de cada oración. Antes se saltan las palabras cuya etiqueta aprendida más frecuente es de preposición (ADP). Se cuenta por separado:
- en preguntas: las preguntas de los ejemplos de lectura, y las oraciones de AnCora con «¿» o «?»;
- en afirmaciones: las demás oraciones de AnCora.

Una palabra es interrogativa si abre al menos 3 preguntas y su tasa equilibrada es de al menos 0,9: (n_p/N_p) / (n_p/N_p + n_a/N_a).
- Se une a lo que G-41 aprende de los rasgos.
- Es el mismo criterio de G-35: al menos 3 apoyos y al menos el 90 %.

Medición previa, hecha solo con los datos de educación (2000 preguntas MLQA y 13 993 afirmaciones de AnCora `train`):
- pasan qué, quién, cuál, cuándo, dónde, cómo, cuántos, cuántas, cuánto, cuáles, quiénes, cuánta, «nombra» y «donde» (sin tilde);
- no pasan el, la, los, un, es, que, si ni cuando.

### 2. Una sola vía de abstención

Si una pregunta interpretada como consulta formal da «desconocido», se consulta la memoria literal antes de abstenerse, igual que una pregunta no interpretada:
- la verificación de G-41 para las de sí o no;
- la alineación del punto 3 para las abiertas.

La abstención por falta de dato empieza siempre por «No lo sé». Es el principio de G-41, que esta vía no seguía.

### 3. Alineación estructural: la pregunta como oración con hueco

Aplica a una pregunta abierta, es decir, con una interrogativa aprendida.

**Preparación de la pregunta**
1. Se analiza con la sintaxis aprendida.
2. **Frase interrogativa:** la interrogativa más su núcleo nominal, si lo tiene («qué color», «cuántos hijos»). El núcleo es la cabeza de la interrogativa si es un sustantivo o, si no, la palabra siguiente cuando es un sustantivo.
3. **Palabras obligatorias:** las que quedan fuera de la frase interrogativa y cuya etiqueta aprendida no es de función. Las de función son: artículo o determinante, preposición, auxiliar, pronombre, conjunción y puntuación.

**Oraciones candidatas**
- Son las de la memoria que contienen todas las raíces obligatorias (intersección de las listas del índice).
- Cada una se analiza una sola vez y el análisis se guarda con ella. Se piensa despacio una vez.

**Respuestas candidatas**
- **Palabras alineadas:** las de la oración cuya raíz aparece en la pregunta.
- **Candidata:** todo subárbol máximo sin palabras alineadas que tenga al menos una palabra que no sea de función.
- Si el núcleo nominal de la frase interrogativa está alineado en la oración, solo cuentan los subárboles que dependen de él. Ejemplo: en «tres hijos», «tres» depende de «hijos».

**Puntuación**
1. **Espejo del árbol:** Σ sobre las palabras alineadas de |distancia en la pregunta (frase interrogativa → palabra) − distancia en la oración (candidata → palabra)|. Menor es mejor.
2. **Desempate por preposición:** si la frase interrogativa lleva preposición («a qué hora», «de quién»), gana la candidata que lleve la misma.
3. **Desempate por función sintáctica:** gana la candidata con la misma función que la interrogativa (por ejemplo, objeto).

**Decisión**
- **Ambigüedad:** si después de desempatar quedan candidatas distintas con la misma puntuación, sea en una oración o en varias, **no se elige en silencio**. La respuesta es «No lo sé con seguridad: lo que me dijeron admite más de una respuesta.», sin nombrar las candidatas (nombrarlas podría acertar la clave por casualidad).
- **Respuesta:** el tramo del subárbol ganador, con la oración y su fuente como explicación.
- **Sin oración candidata:** se usa el lector de G-28 sin cambios, como en G-41. Así, la lectura de MLQA, donde casi nunca aparecen todas las palabras de la pregunta, no cambia.

**Interruptor de ablación:** `structural_answers`. Apagado, las preguntas abiertas van al lector de G-28 como en G-41, conservando el punto 1.

### 5.8

- **Qué fallo resuelve:** las preguntas abiertas en conversación (causas 1–3).
- **Por qué no bastan los actuales:** el lector de G-28 no usa estructura. En G-30, la estructura metida *dentro* de su elegidor bajó el F1 de MLQA. Aquí la estructura solo decide cuando una oración contiene todas las palabras obligatorias, que es el régimen de la conversación, y deja intacto el de la paráfrasis.
- **Qué lo distingue:** la ablación, que apaga solo la alineación; el F1 de MLQA sin cambio; los controles de G-41.
- **Qué se elimina si funciona:** el elegidor de tramos deja de decidir cuando hay una oración que cubre la pregunta. La lista de interrogativas escrita a mano en `_question_like` queda como candidata a retirarse cuando hay educación, en un paso aparte con su propia prueba.

Trabajos cercanos, para ubicar el mecanismo:
- Punyakanok, Roth y Yih (2004), *Mapping dependencies trees: an application to question answering*;
- Wang, Smith y Mitamura (2007), *What is the Jeopardy model? A quasi-synchronous grammar for QA*.

La diferencia es que aquí la sintaxis y las interrogativas son aprendidas por conteo, y que la ambigüedad lleva a abstenerse.

## Evaluación

**Base educada:** la de G-41 (AnCora `train` + 2000 MLQA), reconstruida con el motor de G-42. No usa nada de ningún conjunto de validación.

**Desarrollo (visible):**
- el conjunto de desarrollo de G-41 (30 preguntas);
- la reserva de G-41, ya gastada (33 preguntas);
- un conjunto nuevo de desarrollo, redactado por un subagente con el [encargo fijo](../experiments/validacion_comun_encargo.md) y validado por otro, antes de escribir el código.

**Reserva:** después de `freeze-G-42`, un conjunto **nuevo** con el mismo procedimiento, que no se mira antes de ejecutar. En la reserva se miden:
- **G-42** congelado;
- **G-41** congelado (`freeze-G-41` con su base);
- la estrategia «siempre no lo sé»;
- el **subagente** contestando sin claves.

**Controles:**
- ablación (`structural_answers = False`);
- sin memoria de conversación;
- memoria barajada;
- nombres renombrados.

**Correcciones del evaluador, fijadas antes del código** (defectos hallados en G-41; el veredicto de G-41 no se recalcula):
- «Afirma lo falso» excluye toda abstención de la lista `ABSTENCIONES` de `validacion_comun.py`. En G-41 contaba «No tengo información suficiente…» como falso.
- El renombrado se mide como **invariancia**: la respuesta con nombres cambiados debe ser la respuesta original con los mismos cambios. En G-41, las claves escritas como expresión regular no se renombraban: por eso el control bajó de 14 a 10, aunque el motor dio la misma respuesta en 32 de 33 preguntas.

## Puerta

| Criterio | Umbral |
|---|---|
| Aciertos de G-42 en la reserva | ≥ 60 % de las preguntas y ≥ G-41 congelado + 5 |
| Sí o no falsos (afirmar lo contrario de la clave, sin contar abstenciones) | ≤ 1 |
| Respuestas abiertas equivocadas (no abstención y sin acierto) | ≤ 3 |
| Aporte de la alineación: G-42 − ablación | ≥ +4 |
| Memoria barajada | 0 aciertos en preguntas abiertas y de sí o no |
| Renombrado: respuestas invariantes | ≥ 90 % |
| Lectura MLQA en desarrollo limpio (G-28b) | F1 sin bajar más de 0,005 frente a 0,2221 |
| Regresión completa | sin fallos nuevos |
| Latencia fija intercalada | ≤ +20 % |
| Respuesta en conversación | p95 ≤ 200 ms |

La brecha con el subagente se informa sin maquillarla. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Cuando alguien le cuenta a Leobot «Marta tiene tres hijos» y luego le pregunta «¿Cuántos hijos tiene Marta?», Leobot tiene que hacer lo que hace una persona: poner la pregunta al lado de lo que oyó, ver que casi todo coincide y que el único hueco, el «cuántos», cae justo donde la frase dice «tres». Hoy no lo hace por tres razones:
- no sabía que «cuántos» y «cómo» son palabras de pregunta, porque el libro con el que aprendió casi no las tenía o las tenía mal marcadas;
- a veces contestaba «no tengo información» sin revisar lo que se le había contado;
- elegía la respuesta por costumbre y no por el lugar que ocupa en la frase.

Ahora aprenderá las palabras de pregunta mirando cuáles suelen empezar preguntas y casi nunca empiezan afirmaciones. Revisará siempre lo que se le contó. Y buscará la respuesta en el lugar exacto del hueco. Si dos respuestas le parecen igual de buenas, dirá que no está seguro en vez de adivinar.
