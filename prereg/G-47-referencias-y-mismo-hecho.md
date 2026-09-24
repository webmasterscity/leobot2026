# G-47 — referencias y «dice lo mismo de la misma entidad»

Fecha: 2026-09-24. Preregistro previo al código. Base: `freeze-G-46b` (árbol `dc4481e4`).

## Fallo medido

- **Prueba común del usuario** (32 preguntas de otro autor; el conjunto no se leyó): 16/32.
  - Anáfora («su», «él», «la») 0/5.
  - 3 respuestas equivocadas dichas con seguridad, todas de un tipo distinto al pedido: un color contestado con otro adjetivo o con una relativa; una edad contestada con el número de otra entidad.
- **Reserva doble de G-46b, ya gastada:** 40/63; subagente 62/63. Hubo 23 fallos:
  1. **Otra aparición, otra entidad** (3 casos).
     - «Luis tiene ocho años y Elena tiene doce años» → «¿Cuántos años tiene Elena?» → «ocho». El núcleo de la pregunta («años») se ancla a su **primera** aparición en la oración, y la distancia suma **todas** las apariciones. Una alineación debe ser una correspondencia: una aparición por palabra.
     - «La caja roja tiene siete cuadernos y está en el garaje» → «¿Dónde está la caja roja?» → «siete cuadernos». En el árbol mejorado, el verbo coordinado queda como otra raíz, sin camino hasta su sujeto. La verificación sí usa el sujeto compartido (grafo de G-43); la alineación abierta no.
     - «El hermano de Marta se llama Diego y vive en Loja» → «¿Marta vive en Loja?» → «Sí». El camino pasa por «hermano», otra entidad, y cabe en la holgura de +1 paso.
  2. **Pregunta con el verbo delante** (4 casos): «¿Vende la ferretería materiales eléctricos?». El analizador toma el sujeto por objeto y cuelga el objeto del sujeto. El enlace de la pregunta no existe en la oración, aunque las mismas palabras estén unidas a través del verbo alineado.
  3. **Tipo de respuesta** (2 casos): «¿Cuántas gallinas…?» → «blancas»; «¿Sobre qué…?» → un nombre.
  4. **Número compuesto partido** (1 caso): «cuarenta y dos» se analiza como dos modificadores hermanos, y la respuesta fue «dos».
  5. **Negación en una respuesta abierta** (1 caso): «Julia no revisó si…» → «¿Quién revisó el paquete?» → «Julia».
  6. **Referencias** (4 casos): «su hija Norela», «tiene su sede», «lo presentó», «el padre de ambos».
  7. Paráfrasis o inferencia (8 casos) y una clave discutible. **No se atacan aquí.**

## Cambio (5.8)

### 1. Referencias (interruptor `reference_resolution`)

- **Qué se aprende de AnCora `train`.** Con la sintaxis se cuentan los rasgos morfológicos (FEATS) de pronombres, determinantes, sustantivos y verbos: persona, número, género, posesivo, reflexivo y caso. Al consolidar, cada forma toma sus rasgos mayoritarios con la regla de G-35 (apoyo ≥ 3 y ≥ 90 %). Son referentes los pronombres personales de tercera persona no reflexivos y los posesivos de tercera persona.
- **Verbos impersonales.** Son los lemas verbales con apoyo ≥ 30 y sujeto explícito en menos del 5 % de sus apariciones («haber»). Las proporciones se miden en AnCora.
- **Cuándo se resuelve.** Al necesitar una oración dicha en conversación, se resuelven en orden todas las anteriores aún sin resolver. El resultado se guarda en la fila y no depende del momento en que se pregunte.
- **Qué se resuelve.**
  - Un pronombre de tercera persona.
  - Un posesivo de tercera persona («su hija» → «hija de ANT»).
  - Un **sujeto omitido**: un verbo finito de tercera persona sin sujeto propio ni heredado por coordinación, cuyo lema no es impersonal.
- **Antecedente.** Es la mención nominal (sustantivo o nombre propio, con sus partes de nombre) de mayor prominencia compatible:
  1. para un posesivo, el sujeto de su misma cláusula si va antes y no contiene al posesivo;
  2. el sujeto (ya resuelto) de la oración anterior más reciente que tenga uno;
  3. las demás menciones, de la más reciente a la más antigua, en las últimas 5 oraciones de la conversación.
- **Filtros del antecedente.**
  - Género y número deben concordar cuando ambos se conocen. El de la mención sale de su determinante o de su forma. Un rasgo desconocido es compatible.
  - Un pronombre objeto no se refiere al sujeto de su propia cláusula.
- **Qué se guarda.** Una copia resuelta del árbol:
  - el pronombre se sustituye por el núcleo del antecedente;
  - el posesivo, por «de» + núcleo, que depende del sustantivo poseído;
  - el sujeto omitido se añade como sujeto del verbo.
  El texto original no cambia y es el que se muestra. Las palabras añadidas entran en el índice de búsqueda de esa fila.
- **Qué no se resuelve:** primera y segunda persona, «ambos» y los plurales coordinados.

### 2. Dice lo mismo de la misma entidad (interruptor `same_fact`)

Es una sola comprobación para las preguntas abiertas y para las de sí o no:
- **Una aparición por palabra.** Cada palabra de la pregunta se alinea con la aparición de la oración que mejor encaja en su posición, y el núcleo de la frase interrogativa puede anclarse a cualquiera de sus apariciones. El espejo suma, por cada palabra de la pregunta, la mejor diferencia de distancia entre sus apariciones.
- **Distancias en el mismo grafo.** Las preguntas abiertas miden distancias en el grafo de G-43, con coordinados y sujeto compartido, igual que la verificación.
- **Sin otra entidad en medio.** Un enlace de la pregunta se cumple si hay un camino entre las palabras alineadas que:
  - no pasa por un sustantivo, un nombre propio ni un pronombre no alineados;
  - puede pasar por palabras alineadas y por palabras de función;
  - tiene como máximo los pasos de contenido de la pregunta + 1.
  Se pierde la holgura por entidades ajenas y se tolera el error de enganche de la pregunta con el verbo delante.
- **Misma preposición.** Cada palabra alineada lleva la misma preposición en la pregunta y en la oración, o ninguna en las dos. Esto protege el papel sin depender del enganche de la pregunta.
- **Afirmado y con la misma polaridad.** Una respuesta abierta solo sale de una oración:
  - cuyo predicado alineado no está negado (con un negador aprendido que la pregunta no tiene);
  - y que no está subordinada, con la regla de G-43.
- **Coordinación partida.** Los hermanos sin alinear con la misma función, contiguos y unidos solo por una conjunción o una coma, forman una sola respuesta («cuarenta y dos»).

### 3. Tipo de respuesta como filtro (interruptor `answer_type`)

- **Qué se guarda.** Cada ejemplo de lectura de la educación guarda la clave de la pregunta y la clase de su respuesta (G-43), no el texto:
  - **clave:** la primera interrogativa aprendida, más el sustantivo que la sigue si lo hay;
  - **clase:** la etiqueta mayoritaria de la primera palabra de contenido.
- **Filtro.** Una candidata queda descartada si su clase **nunca** apareció entre ≥ 30 ejemplos de su clave. Se usa la clave con sustantivo si tiene ≥ 30 ejemplos; si no, solo la interrogativa.
- **Por qué filtro y no costo.** Como costo blando, en G-43 no sumó aciertos. Aquí la medida es otra: los errores dichos con seguridad.

5.8:
- **Qué fallo resuelve:**
  - las respuestas de otra entidad o de otro tipo, dichas con seguridad;
  - los sí/no a través de otra entidad;
  - la pregunta con el verbo delante;
  - lo negado dado como respuesta;
  - los datos dichos con referencias.
- **Por qué no bastan los actuales:**
  - la alineación trata las apariciones como un conjunto;
  - la verificación depende del enganche de la pregunta y admite +1 paso por cualquier palabra;
  - nada resuelve una referencia.
- **Qué lo distingue:** la ablación de cada interruptor y de los tres juntos.
- **Qué se elimina:**
  - el primer anclaje del núcleo;
  - la distancia en el árbol sin sujeto compartido;
  - la holgura por entidades ajenas.

## Evaluación

- **Desarrollo:** los 10 conjuntos de conversación gastados (439 preguntas), incluida la reserva doble de G-46b.
- **Reserva doble nueva**, con el mismo procedimiento y el mismo encargo fijo, después de `freeze-G-47`.
- **Conjunto de referencias nuevo:**
  - unas 24 preguntas, redactadas después de congelar por un subagente independiente, con un encargo solo sobre datos dichos con «él», «ella», «lo», «la», «su», «sus» o con el sujeto omitido, preguntados después con el nombre explícito;
  - incluye sí/no y «no lo sé»;
  - lo valida otro subagente;
  - no se mezcla con la reserva doble.
- **MLQA:** los 105 casos de la partición `dev` que nunca se usaron (fuera de la porción del tablero y de las reservas de G-28 y G-28b), porque el fondo de `test` no visto se agotó en G-46b.
- **Se miden:**
  - G-47, `estable-G-11` y el subagente;
  - las ablaciones de `reference_resolution`, `same_fact` y `answer_type`, y la de los tres juntos;
  - sin memoria, barajada y renombrado.

## Puerta

| Criterio | Umbral |
|---|---|
| Aciertos en la reserva doble | ≥ `estable-G-11` + 3 |
| Aporte en la reserva doble (G-47 − los tres interruptores apagados) | ≥ +3 |
| Conjunto de referencias | ≥ 50 % y ≥ `estable-G-11` + 5 |
| Afirma lo falso (sí/no contrarios a la clave), en cada conjunto | ≤ 2 en la reserva doble, ≤ 1 en referencias |
| Respuestas abiertas equivocadas | ≤ 15 % de las abiertas, en cada conjunto |
| Claves «no» acertadas en la reserva doble | ≥ 40 % |
| Memoria barajada | 0 aciertos en abiertas y sí/no |
| Renombrado | ≥ 90 % |
| MLQA (105 `dev` no usados) | F1 ≥ lector de G-28 solo − 0,005 |
| Regresión completa, latencia intercalada con `estable-G-11`, p95 en conversación ≤ 200 ms | como en G-46 |

Si pasa: verificación independiente 5.10 y `estable-G-12`. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Una persona que escucha «Doña Esperanza hizo un sancocho. La reunión fue en casa de su hija Norela» entiende que Norela es hija de Esperanza. Leobot no lo entendía: el «su» no apuntaba a nadie. Ahora buscará a quién se refiere cada «su», «él», «ella», «lo» o «la», y también de quién se habla cuando la frase no lo repite. Para elegir, se fijará en de quién se venía hablando y en si es hombre o mujer, uno o varios, como aprendió en el libro de gramática.

Además, revisará que la respuesta hable de la misma persona o cosa por la que le preguntan. Si le dicen «Luis tiene ocho años y Elena tiene doce» y le preguntan la edad de Elena, no contestará con la de Luis. Si le preguntan «¿cuántas?», no contestará con un color. Y si le dijeron que alguien **no** hizo algo, no lo dará como quien lo hizo.
