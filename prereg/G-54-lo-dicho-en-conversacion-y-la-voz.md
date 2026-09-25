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

## Enmienda antes de congelar (2026-09-24), por lo visto al programar y en desarrollo

**Diseño, precisado al programar** (sin ver aún las cifras de desarrollo):
1. **Valor negado.** Cuenta solo si el negador cuelga de un valor (nombre, número, adjetivo o adverbio), no de un verbo. «Dijo que no viene» es lo que se dijo, no algo negado. El valor negado sale también del tramo de la respuesta: «doce, no trece» → «doce».
2. **Quién habla.**
   - Un clítico de primera persona cuyo verbo también es de primera persona («me llamo») es el propio sujeto y no se sustituye.
   - Las frases posteriores buscan su antecedente en la copia **sin** el nombre de quien habla: una tercera persona («ella», un sujeto omitido de tercera) nunca es quien habla.
   - Si se dan dos nombres, vale el último.
   - Una forma verbal con persona aprendida es finita. `VerbForm` no está entre los rasgos que se guardan.
3. **Lo último dicho, en sí o no.** Solo se aplica lo preregistrado: un valor distinto dicho después en el mismo lugar reemplaza al que coincidía. «Tiene un gato» y después «no tiene un gato» sigue siendo una contradicción que se informa, porque así lo exige la prueba de G-41 (`test_contradiction_is_not_resolved_silently`), y no se resuelve en silencio.
4. **Respuesta completa** (`answer_constituent`). Las partes de un nombre (UD `flat`) del mismo núcleo, contiguas, forman un solo nombre («Santa Ana»). Es la definición de `flat` en UD.
5. **Referencias** (`dative_copy`, punto 6).
   - Al sustituir un clítico dativo por su antecedente, la copia lleva la preposición del dativo aprendida de AnCora (G-49, «a»). Sin ella, «¿A Valentina le van a regalar…?» no se podía colocar, porque G-47 exige las mismas preposiciones.
   - En el objeto directo no se añade nada: en AnCora solo el 49 % de los nombres propios objeto llevan «a» (420 de 852), así que no hay mayoría aprendida.
6. **Voz.**
   - Las respuestas abiertas **no cambian**. Varias pruebas existentes fijan su texto exacto («doce», «Arica»), y el constituyente solo ya es como contesta una persona.
   - La voz cambia las de sí o no, el contraste, la contradicción y «no lo sé».
   - Las personas del plural no se vuelven a decir, porque dependen de la variante del español («ustedes» o «vosotros»). Si una palabra de la frase no tiene forma conocida, la respuesta queda en «Sí, me lo contaste.».
   - Las formas se cuentan también en **UD GSD `train`** (texto web escrito por personas, CC BY-SA 4.0), solo para la tabla de formas: AnCora tiene 387 formas de segunda persona del singular, GSD 346 y COSER 125.
7. **Formas, precisado en desarrollo** (ninguna cifra de aciertos cambia con esto; solo la voz):
   - **Qué se cuenta.** Se cuentan las formas verbales de **todas** las personas, y las de pronombres y posesivos de primera y segunda. Así se ve que «cantaba» o «tenía» valen para dos personas.
   - **Ambigüedad de persona.** Una forma de más de una persona toma la del sujeto o del clítico de su oración. Si no hay, no se vuelve a decir.
   - **Ruido de anotación.** Una lectura vista menos de 3 veces, junto a otra que llega a 3, es ruido. Es el apoyo de G-35.
   - **Forma nunca contada.** Se analiza con las reglas de terminación y solo con lemas conocidos.
   - **Forma nueva.** Se hace con la regla de la misma terminación del lema que produce la forma de partida. Por eso «hice» no da «haciste».
   - **Fuentes.** **GSD se retira** de la tabla de formas porque mezcla el voseo («salís»). Quedan AnCora y COSER.
8. **Quién habla y la preposición del hueco** (`gap_case`). Cuando la frase interrogativa lleva preposición («¿**con** quién?», «¿**a** dónde?»), la candidata con esa preposición va antes que las distancias en el árbol. Si el sustantivo de la frase está colocado, la candidata sin preposición.
   - Casos en desarrollo: «¿A dónde viajó Laura?» → «en autobús»; «¿Con quién es la reunión?» → «el jueves».
9. **Nombre propio como respuesta** (`name_kind`). Corrige el defecto de G-53 que encontró la auditoría. Un nombre propio no necesita haberse visto solo donde los nombres son una clase aprendida de respuestas a esa clase de pregunta (≥ 10 %). Así, un nombre ya no es un color.
10. **Lo último dicho en sí o no.** El valor posterior reemplaza al preguntado solo si los dos son miembros de una misma clase cerrada aprendida (G-53: «martes» y «lunes» responden a «qué día»). En desarrollo, «compró una bicicleta nueva» contradecía «¿La bicicleta es verde?».
11. **Alcance del negador en la aposición.** Una palabra en aposición o parte de un nombre está en el alcance del negador que cuelga del sustantivo al que acompaña: «…, no su colega Tomás». Es la misma frase nominal.
12. **Coordinación en la respuesta de identidad.** Si el sustantivo preguntado es plural («¿Cómo se llaman las hijas…?»), la respuesta es la coordinación entera: «Lucía y Paula».
13. **Parte de nombre.** Un `flat` se une a las palabras contiguas anteriores del mismo núcleo. «San Jorge»: el analizador cuelga las dos partes del sustantivo.

**Evaluación, precisada antes de congelar:**
- **Errores confiados.** Se añade la métrica que faltaba según la auditoría: una respuesta con contenido a una clave «no lo sé» es un error dicho con seguridad. La puerta «afirma lo falso ≤» se aplica a la suma de los tres tipos: afirma lo falso, abiertas equivocadas y contenido con clave «no lo sé».
- **G-52 se vuelve a medir.** Su ablación va en los tres conjuntos juntos. **Si su aporte es ≤ 0, se retira** (5.9), con la misma regla que se aplicó a G-49 y G-51.
- **Controles pendientes de G-53.** Se miden en el material nuevo:
  - la base con clases solo de MLQA (`base_educada --clases-mlqa`);
  - la ablación `answer_kind`;
  - las equivocadas por clase de pregunta.
- **Procedimiento.**
  - Los conjuntos nuevos se guardan en git **antes** de ejecutar Leobot sobre ellos.
  - Los redactores son subagentes nuevos, lanzados con la herramienta Agent y sin el mensaje del usuario. Un flujo orquestado reenvía ese mensaje a cada subagente, así contaminó la reserva de G-52.
14. **Preposición del hueco: solo orden, no exclusión.** Primero se probó descartar las candidatas con otra preposición. En desarrollo se perdieron dos respuestas legítimas: «desde las cinco» a «¿A qué hora abre?» y «de su hermana menor» a «¿Con quién volvió?». Se deja solo el orden. Además cuentan las preposiciones de los complementos directos de la candidata: «de Barranquilla a Cartagena», porque el analizador colgó «a Cartagena» de «Barranquilla».
15. **Núcleo de un nombre unido.** El núcleo del grupo es el nombre propio. Si no, la comprobación de clase lo tomaba por el adjetivo «San».
16. **Coordinación en la identidad.** El plural se toma del sustantivo de la **pregunta**. Un coordinado no se da por separado de su coordinación.

**Desarrollo** (20 conjuntos gastados, 968 preguntas; la ablación completa reproduce `freeze-G-53r`: 86/129 y 26/48):

| Corrida | Aciertos | Abiertas equivocadas | Afirma lo falso | Ganadas / perdidas frente a la ablación |
|---|---|---|---|---|
| ablación completa (= `freeze-G-53r`) | 718 | 22 | 5 | — |
| 1.ª versión | 721 | 19 | 5 | +4 / −1 |
| con los puntos 8 a 11 | 724 | 16 | 5 | +6 / −0 |
| con exclusión por preposición | 723 | 13 | 5 | +7 / −2 |
| puntos 14 a 16 | *interrumpida por falta de memoria del equipo (170/968: +1 / −0)* | | | |

Los conjuntos de desarrollo están todos en tercera persona. Por eso casi no miden «quién habla» ni la voz; eso lo mide la charla nueva.

## Resultado (2026-09-25, `freeze-G-54`, árbol `0d5eda1e`)

**Material nuevo.**
- Se escribió después de congelar, con subagentes nuevos (herramienta Agent) que no recibieron el mensaje del usuario, y lo validaron otros subagentes.
- Entró en git (`50a5c1e`) antes de ejecutar Leobot.
- Base congelada idéntica byte a byte a la de desarrollo (`67905a5e`).

| Conjunto | G-54 | Sin el contenido de G-54 | `estable-G-13` | Sin G-52 | Sin G-53 | Clases solo de MLQA | Subagente |
|---|---|---|---|---|---|---|---|
| Reserva cuádruple (127) | 96 | 96 | 96 | 94 | 95 | 94 | 125 |
| Referencias (48) | 30 | 30 | 30 | 28 | 31 | 29 | 48 |
| Charla (64) | 30 | 31 | 31 | 30 | 29 | 30 | 64 |
| **Total (239)** | **156** | **157** | **157** | **152** | **155** | **153** | **237** |

**Controles.** Reinicio: respuestas idénticas en el 100 %. Memoria barajada y sin memoria: 0 aciertos en abiertas y sí/no. Renombrado: 123/127, 48/48 y 64/64.

**SQuAD-es 2400:** G-54 0,2375; sin G-54 0,2378; lector solo 0,2360. Pasa.

**Errores confiados** (afirma lo falso + abiertas equivocadas + contenido con clave «no lo sé»):
- con G-54: 4 + 2 + 3 = 9;
- sin G-53: 6 + 1 + 7 = 14.

**Puerta del contenido (puntos 1 a 6 y enmienda): no pasa.**
- Aporte: −1 en los tres conjuntos juntos. Cada interruptor aporta 0.
- Salvo `scoped_polarity`, que aporta −1 y suma 1 afirmación falsa en la charla: «¿Fue mi papá al almuerzo?» → «Sí, me contaste que tu papá no fue…». El «no» colgaba del verbo, y la pregunta analizó «Fue» como auxiliar no colocado. El alcance correcto incluye la cabeza de la oración que gobierna las palabras colocadas.
- El +6 de desarrollo no se repitió: estos fenómenos casi no aparecen en el material nuevo.
- **Retirada (5.9):** se retiran los ocho puntos de contenido: `scoped_polarity`, `negated_value`, `speaker`, `recency`, `answer_constituent`, `dative_copy`, `name_kind` y `gap_case`. Ninguno redujo las afirmaciones falsas ni las abiertas equivocadas en la reserva. Su código queda en `freeze-G-54`, por si otra medida externa, como la prueba común del usuario, mostrara lo contrario. Eso pediría un preregistro nuevo.

**Puerta de la voz: pasa.** Juez a ciegas, subagente nuevo, 64 preguntas de la charla:

| | Naturalidad media (1–5) | Errores gramaticales |
|---|---|---|
| Leobot con voz | **3,08** | 1 |
| Leobot sin voz | 1,89 | 1 |
| Subagente | 4,63 | 0 |

- Diferencia: +1,19 ≥ +0,5.
- Aciertos idénticos con voz y sin voz en los tres conjuntos.
- Errores gramaticales: 1,6 % ≤ 5 %.
- La voz se queda: formas aprendidas de AnCora y COSER.

**Retirada de G-52 (enmienda): no se retira.** Aporta +4 (+2 en la reserva y +2 en referencias). Queda confirmado.

**Controles pendientes de G-53:**
- las clases contadas en SQuAD-es aportan +3 frente a contarlas solo en MLQA (156 frente a 153);
- abiertas equivocadas: 4 frente a 6;
- G-53 frente a su ablación: +1 en aciertos y 9 errores confiados frente a 14.

**Causas de los 34 fallos de la charla** (material ya gastado, pasa a desarrollo):
- el complemento de la frase interrogativa se exige a la frase («¿qué día **de la semana**…?»): 4;
- palabras de la pregunta que no hacen falta («**ya**», «**ahora**»): 5;
- datos repartidos entre dos frases sobre la misma entidad: unos 5;
- errores del analizador en preguntas con el verbo delante, que rompen los enlaces estrictos: unos 9;
- paráfrasis: el resto.

Siguiente: G-55 (el «no» por la clase aprendida) y un ciclo para la charla con esas causas.

## Verificación independiente 5.10 de `freeze-G-54r` (2026-09-25)

[Informe](../results_v3/auditoria_g54r.md). **Confirma.**
- La base es idéntica byte a byte.
- En los tres conjuntos da 96, 30 y 31, igual que `estable-G-13`.
- La voz no cambia ningún acierto.
- Con `PYTHONHASHSEED=1` las respuestas son idénticas.
- Las referencias de `freeze-G-54` dan las mismas cifras.
- El juicio de naturalidad se recalcula exacto.

Salvedades registradas:
1. **Palabras propias de la voz no declaradas antes:** «lo contrario» («No, me contaste lo contrario.») y «eso» («No lo sé: eso no me lo has contado.»). Se declaran aquí como programadas: son voz de quien responde, no conocimiento. El umbral `FORM_RULE_SUPPORT = 2` tampoco estaba declarado.
2. **El juicio de naturalidad completo** (preguntas, mapa, notas del juez y respuestas) se guarda ahora en [`results_v3/g54_naturalidad_juicio/`](../results_v3/g54_naturalidad_juicio/). El juez vio las respuestas de `freeze-G-54`; en `freeze-G-54r` coinciden 63 de 64, y la distinta es mejor.
3. **Orden de los commits:** la enmienda es del mismo segundo que el código. Precede al tag, pero git no demuestra que preceda al código; es la misma salvedad que en G-53.
4. **«Eso no me lo has contado»** sale también cuando la pregunta es sobre un documento leído.
5. **Errata:** el commit `50a5c1e` dice «charla 65»; son 64 preguntas calificadas.
