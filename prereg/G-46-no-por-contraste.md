# G-46 — «no» cuando se dijo otro valor del mismo atributo

Fecha: 2026-09-24. Preregistro previo al código. Base: `estable-G-11` (árbol `b9038ee5`).

## Fallo medido

Las preguntas de sí o no cuya clave es «no» fallan siempre: 0/6 en la reserva doble de G-44b y 0/7 en la de G-45. Casi todas se deben a un contraste, no a una negación explícita:
- «Tomás compró un carro azul» → «¿El carro de Tomás es rojo?» → no;
- «La farmacia cierra a las nueve» → «¿cierra a las diez?» → no;
- «Andrés trabaja en un banco» → «¿trabaja en un hospital?» → no;
- «En la caja hay doce manzanas» → «¿hay quince manzanas?» → no.

La verificación de G-43 busca una oración que diga lo mismo o lo contrario con negación. No reconoce otro valor en la misma casilla.

**Límite medido:** la tasa de coordinación por casilla en AnCora no separa las casillas de un solo valor de las de varios («tener» objeto 4 %, «haber» objeto 5,8 %, «estar en» 5,4 %). Por conteo de coordinaciones no se puede aprender qué casilla admite un solo valor.

## Cambio (5.8)

**Contraste estructural.** Si ninguna oración apoya la pregunta de sí o no, se busca una que:
1. alinee, con la estructura de G-43 (enlaces entre palabras de contenido, palabras de función transparentes), todas las palabras de contenido de la pregunta menos una, el **valor preguntado** `v`;
2. tenga una palabra no alineada `w` con la **misma etiqueta aprendida** que `v`, a la misma distancia (un paso de contenido) de la palabra de la oración alineada con el vecino de `v` en la pregunta, y con otro lema;
3. no sea negativa ni subordinada.

**El atributo es de un solo valor si** `v` y `w` son adjetivos o números, o si `w` va con preposición, o si `w` es atributo de un verbo copulativo. Un objeto directo nominal (lo que se tiene, lo que hay, lo que se vende) no lo es: tener una bicicleta no excluye tener una moto. Este principio es general y estructural: los atributos (cualidades, cantidades, lugares y tiempos) toman un valor por entidad; las entidades poseídas o existentes no.

- **Respuesta:** «No: según lo que me dijeron, …» con la oración.
- **Interruptor:** `contrast_answers`.

5.8:
- **Qué fallo resuelve:** el «no» por otro valor.
- **Por qué no bastan los actuales:** la verificación solo reconoce la misma afirmación o su negación.
- **Qué lo distingue:** la ablación; los falsos «no» en las claves «no lo sé» y «sí».
- **Qué se elimina:** nada. El mecanismo se añade a la verificación y reutiliza sus enlaces.

**Riesgo conocido:** dos adjetivos de distinta dimensión («azul» y «grande») darían un «no» falso. Se mide como «afirma lo falso».

**Enmienda antes de congelar (2026-09-24), por lo visto en desarrollo** (8 conjuntos gastados, 314 preguntas). La primera versión exigía el rasgo de atributo solo en la oración. Dio 241 frente a 229 de la ablación, con «no» 22/35 frente a 6/35, pero hubo 4 «no» falsos. En dos de ellos, el valor preguntado ocupaba otra casilla que la palabra de la oración: «¿vende pescado?» (objeto) frente a «de don Alberto»; «¿tiene tulipanes?» frente a «con rosas». Por eso el principio se aplica a los dos lados:
- el valor preguntado también debe estar en un lugar de atributo;
- los dos deben llevar la **misma preposición**, o ninguna.

Los otros dos casos no cambian: «¿Fue caro el sombrero?» frente a «azul» es el riesgo conocido de dimensiones distintas, y «¿Marta vive en Toledo?» frente a «vive en Salamanca» choca con una clave «no lo sé» que puso el validador. La puerta no cambia.

## Evaluación

- **Desarrollo:** los 8 conjuntos de conversación gastados (314 preguntas).
- **Reserva doble nueva** después de `freeze-G-46` (evaluador de G-45 con el recuento trivial corregido: una respuesta fija «No lo sé» también acierta las claves «sin afirmar»).
- **MLQA:** 600 casos no vistos, excluidos también los 300 del tramo `chosen[2000:2300]` que G-28 usó como desarrollo (salvedad de la auditoría de G-45).
- Se miden G-46, `estable-G-11`, el subagente, la ablación, sin memoria, barajada y renombrado.

## Puerta

| Criterio | Umbral |
|---|---|
| Aciertos en la reserva doble | ≥ `estable-G-11` + 3 |
| Claves «no» acertadas | ≥ 40 % |
| Aporte (G-46 − ablación) | ≥ +3 |
| Afirma lo falso (sí/no contrarios a la clave, sin abstenciones) | ≤ 2 |
| Respuestas abiertas equivocadas | ≤ 15 % de las abiertas |
| Memoria barajada | 0 aciertos en abiertas y sí/no |
| Renombrado: respuestas invariantes | ≥ 90 % |
| MLQA no vista (600) | F1 ≥ lector de G-28 solo − 0,005 |
| Regresión completa | sin fallos nuevos |
| Latencia fija intercalada con `estable-G-11` | ≤ +20 % y dentro de presupuestos |
| Respuesta en conversación | p95 ≤ 200 ms |

Si pasa: verificación independiente 5.10 y `estable-G-12`. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Si a Leobot le cuentan que el carro de Tomás es azul y le preguntan si es rojo, hoy dice «no lo sé». Una persona diría «no», porque un carro tiene un solo color. Ahora Leobot dirá «no» cuando le pregunten por otro valor de una cualidad (el color), de una cantidad (cuántos), de un lugar o de un momento que ya le dijeron. Pero si le cuentan que Laura tiene una bicicleta y le preguntan si tiene una moto, seguirá diciendo «no lo sé», porque tener una cosa no impide tener otra.
