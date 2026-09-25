# G-54 — lo dicho en una conversación: alcance de la negación, valor negado, quién habla, correcciones y respuesta completa; y la voz de la respuesta

Fecha: 2026-09-24. Preregistro previo al código. **Sugerencia del usuario**, adoptada en parte (abajo, lo que no se toma y por qué). Base: `freeze-G-53r` (árbol `0066ff79`).

## Fallo medido

**Prueba nueva del usuario** (42 preguntas, escrita por un subagente que no conoce a Leobot; el conjunto no se lee): `freeze-G-53r` saca 24/42 (`estable-G-12`, 25), con 6 respuestas equivocadas; Claude, 42/42. Tipos de fallo, según el usuario:
1. **Límites de la respuesta** (5 de las 6 equivocadas): se contesta una parte del constituyente o un constituyente vecino.
2. **Correcciones y cambios** (4): lo dicho después sustituye a lo anterior.
3. **Quién habla** (3): la primera persona es quien habla; si dijo su nombre, «mi X» es «la X de ese nombre».
4. **Negación y contraste dentro de la oración** (3).
5. **Referencias** «le», «sus», «ella» (2–3).
6. **Naturalidad**: «Sí, según lo que me dijeron» suena a máquina.

**Condición del usuario:** nada escrito a mano. Ni listas de palabras, ni expresiones regulares por construcción, ni plantillas de respuesta, ni reglas pensadas para estos ejemplos. Todo sale de conteos en texto escrito por personas, de anotaciones UD, de preguntas resueltas o de principios generales de memoria que no dependen de palabras concretas.

**Causa ya vista en el código** (tipo 4): en las preguntas de sí o no, la polaridad de la frase recordada es la de **todos** sus negadores (`verify_from_utterances`). En las preguntas abiertas se cuentan desde G-47 solo los negadores que cuelgan de las palabras colocadas, es decir, su alcance según UD. «X no vino; Y sí» niega también lo que se pregunta de Y.

## Cambio (5.8)

Cada punto lleva su interruptor, para su ablación.

**1. Alcance de la negación en sí o no** (`scoped_polarity`).
- La polaridad de una frase que apoya la pregunta es la de los negadores aprendidos (G-41, G-52) que cuelgan de una palabra colocada.
- Es la misma regla que ya usan las respuestas abiertas. La unifica.

**2. Un valor negado no es respuesta** (`negated_value`).
- Una candidata abierta de cuyo núcleo cuelga un negador aprendido es lo que se negó, no lo que se afirmó.
- Ejemplo del tipo: «el doce, no el trece».

**3. Quien habla** (`speaker`).
- La primera persona del singular se reconoce por los rasgos aprendidos de AnCora (`Person=1`, `Number=Sing`). Incluye pronombres, posesivos y el verbo finito sin sujeto.
- Se refiere a quien habla en la conversación, que es siempre la misma persona.
- Si la conversación dijo su nombre, con una identidad de G-51 cuyo otro lado es la primera persona (el verbo de identidad aprendido o la cópula), las copias resueltas de G-47 llevan ese nombre:
  - «mi X» → «X» + la preposición aprendida del posesivo (G-49) + el nombre;
  - pronombre → el nombre;
  - verbo sin sujeto → el nombre como sujeto.
- Vale para todas las frases de la conversación, las de antes y las de después del nombre.
- Sin nombre, nada cambia.
- Es un principio de la deixis, no de palabras: sale de los rasgos de persona aprendidos.

**4. Lo último dicho sustituye a lo anterior** (`recency`), un principio general de memoria.
- **Abiertas:** entre frases distintas de la conversación, cuyas candidatas son del tipo pedido y cuya colocación es igual de completa, gana la frase **más reciente**. Así se decide en lugar de «no lo sé con seguridad».
  - Solo se aplica donde G-53 comprueba el tipo: una clase dominante o un sustantivo con miembros.
  - Dentro de una misma frase decide la clave de siempre.
- **Sí o no:** si una frase **posterior** a la que apoya la respuesta dice otro valor en el mismo lugar, la respuesta es «no». El otro valor se reconoce con el contraste de G-46: lugar de atributo y mismo papel.

**5. La respuesta es el constituyente completo** (`answer_constituent`).
- La respuesta es el constituyente completo que da el analizador aprendido, con la clase de G-53.
- Los detalles se fijan con el diagnóstico de desarrollo, en la enmienda: partes de un nombre, coordinación y función del hueco.

**6. Referencias.**
- Los fallos de «le», «sus» y «ella» se diagnostican en desarrollo.
- Si su causa es general y cabe en G-47 o G-51, se corrige allí, con la enmienda y su interruptor.
- La correferencia de AnCora no está en la versión UD disponible. No se descarga nada nuevo sin registrarlo.

**7. La voz de la respuesta** (`answer_voice`).
- **Sí o no:** la respuesta vuelve a decir la frase que la apoya, contada desde quien responde. Por ejemplo: «Sí, me contaste que tu mamá se llama Luz».
- **Cambio de persona.** Las palabras en primera persona pasan a segunda, y al revés. Se genera la forma con el mismo lema y los mismos rasgos salvo la persona. Tres fuentes, en este orden:
  1. una tabla aprendida (lema, clase, rasgos) → forma, contada en UD AnCora `train` y **UD COSER** (habla oral transcrita, CC BY-SA 4.0; `/media/leonardo/data/corpus_ud`), que tiene primera y segunda persona;
  2. sin lema (pronombres y posesivos), la forma más frecuente con esos rasgos;
  3. si la forma no se vio, la terminación aprendida: la sustitución de final de lema a final de forma más frecuente para esos rasgos, según la terminación del lema.
- COSER solo se cuenta para esta tabla de formas. No entra en el analizador ni en los lemas.
- **Abiertas:** el constituyente, con mayúscula inicial y punto final.
- **«No lo sé»:** igual comienzo, con una razón corta.
- **Lo único escrito a mano** son las palabras del propio Leobot: «sí», «no», «no lo sé» (ya existían), «me contaste que» y «no me lo contaste». Es la voz de quien responde, no conocimiento del dominio. Se declaran aquí como programadas.

**Lo que no se toma:**
- «Fue el martes, no, el miércoles». El «no» entre comas es una corrección del hablante. Distinguirlo del «no» que niega el valor siguiente pediría una regla de puntuación escrita a mano. Queda como fallo conocido.

5.8:
- **Qué fallo resuelve:** los tipos 1 a 6 de arriba.
- **Por qué no bastan los actuales:**
  - la polaridad de sí o no no tiene alcance;
  - G-47 solo resuelve la tercera persona;
  - la memoria no ordena lo dicho en el tiempo;
  - la voz es un texto fijo.
- **Qué lo distingue:** una ablación por interruptor, todas juntas, y el juicio a ciegas de la voz.
- **Qué se elimina si funciona:** el conteo de negadores en toda la frase, en sí o no; y el texto fijo «según lo que me dijeron».

## Evaluación

**Desarrollo:** los 20 conjuntos gastados (unas 970 preguntas), incluidas la reserva cuádruple y las referencias de G-52.

**Después de `freeze-G-54`**, redactados por subagentes nuevos (herramienta Agent, copia aislada, nunca un fork ni un flujo orquestado), que **no reciben el mensaje del usuario ni sus ejemplos**:
- **reserva cuádruple**, con el [encargo fijo](../experiments/validacion_comun_encargo.md);
- **referencias**, con el [encargo de referencias](../experiments/g47_encargo_referencias.md);
- **charla doble**, con el [encargo de charla](../experiments/g54_encargo_charla.md), escrito y registrado junto con este preregistro. Ahí una persona cuenta su vida en primera persona y luego pregunta qué se recuerda. El encargo fijo solo produce hechos en tercera persona, así que esta distribución no estaba medida.
- Cada conjunto lo valida otro subagente y lo contesta, sin la clave, un subagente distinto: la comparación de siempre.

**Lectura:** 2400 casos nuevos de SQuAD-es `dev`, excluidos los ya usados, con la semilla de `freeze-G-54`.

**Se miden:**
- G-54, `freeze-G-53r` y el subagente;
- cada ablación y todas juntas;
- sin memoria, barajada, renombrado y reinicio.

**Naturalidad:**
- Un juez nuevo, que no conoce a Leobot, ve la charla, la pregunta y tres respuestas sin rótulo y en orden al azar: G-54 con voz, G-54 sin voz y el subagente.
- Puntúa cada respuesta de 1 a 5, según si suena a lo que diría una persona en esa charla, y marca los errores gramaticales.
- Se juzgan las preguntas de la charla doble.

**Controles no aplicables, con su justificación:**
- **contraevidencia:** la corrección (punto 4) es justamente evidencia posterior; se mide con su ablación;
- **señal confundida:** no hay señal auxiliar aprendida junto con la útil.

## Puertas

**Contenido (puntos 1 a 6):**

| Criterio | Umbral |
|---|---|
| Aciertos en la charla doble | ≥ `freeze-G-53r` + 4 |
| Aciertos en los tres conjuntos juntos | ≥ `freeze-G-53r` + 6 |
| Aporte (G-54 − todas sus ablaciones), los tres conjuntos juntos | ≥ +4 |
| Afirma lo falso, los tres conjuntos juntos | ≤ `freeze-G-53r` |
| Respuestas abiertas equivocadas, los tres conjuntos juntos | ≤ `freeze-G-53r` |
| Reinicio | respuestas idénticas en el 100 % |
| Memoria barajada | 0 aciertos en abiertas y sí/no |
| Renombrado | ≥ 90 % en cada conjunto |
| SQuAD-es `dev` (2400 nuevos) | F1 ≥ lector de G-28 solo − 0,005 |
| Regresión completa, latencia intercalada con `estable-G-12`, p95 en conversación ≤ 200 ms | como en G-46 |

**Retirada (5.9):** se retira cada punto con aporte ≤ 0 en los tres conjuntos juntos que no reduzca las afirmaciones falsas ni las abiertas equivocadas.

**Voz (punto 7):**

| Criterio | Umbral |
|---|---|
| Naturalidad media con voz | ≥ sin voz + 0,5 |
| Aciertos | idénticos con voz y sin voz, en los tres conjuntos |
| Respuestas con error gramatical marcado por el juez | ≤ 5 % |

Se informa la brecha con el subagente.

Si pasan: verificación independiente 5.10 y `estable-G-14`. Si fallan, se registra sin relajarlas.

## En palabras fáciles de entender

En una charla, las personas se corrigen («al final fue el lunes»), hablan de sí mismas («mi mamá se llama Luz») y niegan una cosa mientras afirman otra («él no fue; ella sí»). Leobot se enredaba con eso. A veces daba solo un pedazo de la respuesta y contestaba como una máquina: «Sí, según lo que me dijeron». Ahora aprenderá cinco cosas:
- el «no» afecta solo a lo que niega;
- quien habla en primera persona es la persona que le está contando;
- lo último que se dijo sobre algo reemplaza lo anterior;
- la respuesta va completa;
- al responder, repite lo que le contaron como lo diría una persona: «Sí, me contaste que tu mamá se llama Luz».

Todo sale de lo que aprende de textos escritos por personas, sin listas hechas a mano. Lo medirán exámenes nuevos, escritos por otros que no conocen a Leobot. Un juez que no sabe quién respondió dirá cuál respuesta suena más natural.
