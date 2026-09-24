# G-44 — el lector aprende de sus ejemplos cómo se responde cada pregunta

Fecha: 2026-09-24. Preregistro previo al código. Base: `freeze-G-43b` (árbol `263cc12b`). Quinto diseño de conversación en la fase G.

## Fallo medido

[G-43b](../results_v3/g43b_reserva_hashseed0.json) sacó 18/32 en su reserva (subagente: 31/32), con 7 respuestas abiertas equivocadas. En la [MLQA no vista](../results_v3/g43b_mlqa_reserva.json) quedó 0,019 por debajo del lector de G-28. Causas vistas en la reserva gastada y en desarrollo:

1. **Desempates fijos que no aguantan los errores del análisis.**
   - La regla de preposición prefiere la candidata sin preposición cuando la pregunta no la tiene. Para «dónde», lo normal es «en …», y así ganó «es carpintero» sobre «en Cartago».
   - En MLQA, para «quién» o «cuándo» salen adverbios («También», «Poco a poco»).
2. **El sustantivo de la pregunta se trata igual en todas las interrogativas.**
   - «¿Cuántas gallinas tiene don Alberto?» se contesta con «un huerto», de una oración sin «gallinas».
   - Para «qué color», en cambio, el sustantivo suele faltar en la respuesta.
3. **La raíz de 5 letras confunde palabras distintas** («bibliotecaria» = «biblioteca»).
4. **Interrogativas escritas sin tilde** («¿Cuantos…?», «¿Quien…?»). Se tratan como preguntas de sí o no; en la muestra MLQA de G-43b costaron −0,009.
5. **El lector de G-28 contesta lo que ninguna oración cubre**, también cuando falta el sustantivo que la pregunta cuantifica.

## Cambio (5.8)

### 1. Repaso de los ejemplos trabajados al consolidar

Cada ejemplo de lectura guarda la pregunta, la oración que contiene la respuesta y la respuesta, hasta 5000 ejemplos. Al consolidar la lectura, si hay sintaxis aprendida, se analizan pregunta y oración y se cuenta, para cada interrogativa:
- **preposición de la respuesta:** la preposición que rige el núcleo de la respuesta en la oración, o ninguna;
- **clase del núcleo:** la etiqueta, en contexto, del núcleo de la respuesta;
- **presencia del sustantivo:** si el sustantivo que sigue a la interrogativa aparece, por lema, en la oración que responde.

Así el resultado no depende del orden en que llegan la sintaxis y la lectura. El repaso es pensar despacio una vez, al educar.

### 2. Uso en la alineación estructural

- **Costo de una candidata:** espejo + (−ln P(preposición | interrogativa)) + (−ln P(clase del núcleo | interrogativa)), con suavizado de uno.
- **Clave de orden:** (cobertura; costo; función). El desempate literal por preposición de G-42 se retira. Si quedan empates, el lector de G-28 los resuelve como en G-43.
- **Sustantivo obligatorio:** el sustantivo que sigue a la interrogativa pasa a ser obligatorio si aparece en la oración que responde en al menos el 90 % de los ejemplos, con al menos 10 ejemplos. Esto vale para la alineación y para el lector de G-28: si su oración no lo contiene, la respuesta es «No lo sé».
- **Preposición repetida:** si la frase interrogativa lleva la misma preposición que abre la respuesta («¿A qué ciudad…?» → «a Nueva York»), la preposición no se repite.

### 3. Alineación por lema aprendido

`observe_parsed_sentence` acepta lemas. La forma se asigna a su lema más frecuente. En la alineación estructural y en la verificación de sí o no, dos palabras se alinean si tienen el mismo lema. Una palabra desconocida vale por su forma completa, sin tildes. La búsqueda de oraciones candidatas sigue usando el índice de raíces, que solo propone candidatas.

### 4. Interrogativas sin tilde, solo en la posición donde se aprendieron

En una pregunta, la primera palabra después de las preposiciones cuenta como interrogativa si, sin tildes, coincide con una interrogativa aprendida. Es la misma posición de la que se aprendieron.

**Interruptor de ablación:** `answer_frames` (sin lo del punto 2, con la puntuación de G-43b).

### 5.8

- **Qué fallo resuelve:** las causas 1–5.
- **Por qué no bastan los actuales:** G-42/43 usan un orden fijo; G-43 aprendía la clase fuera de contexto y sin preposición, y se retiró por no aportar.
- **Qué lo distingue:** la ablación `answer_frames`; MLQA no vista; la reserva doble.
- **Qué se elimina:** el desempate literal por preposición y la raíz de 5 letras en la alineación estructural y en la verificación.

La educación de la base agrega los lemas de AnCora `train`, que ya estaban en el mismo archivo. No se agrega ningún dato nuevo.

## Evaluación

**Desarrollo (visible, todo ya gastado):** los 6 conjuntos de conversación usados (desarrollo de G-41 y G-42; reservas de G-41, G-42, G-43 y G-43b) y MLQA visible.

**Reserva doble:** después de `freeze-G-44`, **dos conjuntos nuevos** con el encargo fijo, cada uno validado por otro subagente y unidos en uno, de unas 60 preguntas en total. Así pesa menos la variación entre reservas, que en G-43 y G-43b fue de 26/30 frente a 18/32.

**MLQA no vista:** 600 casos no usados en educación, desarrollo ni muestras anteriores, con la semilla de `freeze-G-44`.

En la reserva se miden:
- G-44;
- G-43b congelado;
- «siempre no lo sé»;
- el subagente sin claves;
- la ablación `answer_frames`;
- sin memoria, memoria barajada y renombrado.

## Puerta

| Criterio | Umbral |
|---|---|
| Aciertos de G-44 en la reserva doble | ≥ 65 % y ≥ G-43b congelado + 3 |
| Aporte de lo aprendido (G-44 − ablación `answer_frames`) | ≥ +2 |
| Sí o no falsos (sin abstenciones) | ≤ 2 |
| Respuestas abiertas equivocadas | ≤ 10 % de las preguntas abiertas |
| Memoria barajada | 0 aciertos en abiertas y sí/no |
| Renombrado: respuestas invariantes | ≥ 90 % |
| MLQA no vista (600), bot educado completo | F1 ≥ lector de G-28 solo − 0,005 |
| Regresión completa | sin fallos nuevos |
| Latencia fija intercalada con `estable-G-10` | ≤ +20 % y dentro de presupuestos |
| Respuesta en conversación | p95 ≤ 200 ms |

Si pasa: verificación independiente 5.10 y `estable-G-11`. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Hasta ahora Leobot usaba reglas fijas para elegir la respuesta. Por ejemplo, «si la pregunta no tiene preposición, la respuesta tampoco». Pero a «¿dónde vive?» se contesta «en Cartago», con preposición. Ahora Leobot aprenderá esas costumbres de sus propios ejemplos de estudio:
- con qué palabra suele empezar la respuesta a cada tipo de pregunta;
- qué tipo de palabra es;
- si la cosa que se pregunta («gallinas» en «¿cuántas gallinas?») tiene que aparecer en la frase que responde.

También reconocerá las palabras por su forma de diccionario, para no confundir «bibliotecaria» con «biblioteca», y entenderá «cuantos» aunque le falte la tilde. Para medirlo con justicia, esta vez el examen tendrá el doble de preguntas.
