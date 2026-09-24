# G-52 — el hueco en el predicado, la negación concordante y el sujeto omitido en plural (más una reserva con potencia)

Fecha: 2026-09-24. Preregistro previo al código. Base: `freeze-G-51` (árbol `dc219b9b`).

## Por qué

**1. Tres causas generales** vistas en las reservas ya gastadas de G-49 y G-51 (150 preguntas):
- **El hueco está en el predicado.** «El coche de Elena es azul» → «¿De qué color es el coche de Elena?» respondió «en Valencia»; «Rocco es un perro pastor alemán» → «¿De qué raza es Rocco?» respondió «a pasear por el parque…».
  - La respuesta de G-42 es el subárbol más grande sin palabras de la pregunta. El predicado de una cópula domina a su sujeto, así que nunca es candidato.
  - La interrogativa de estas preguntas ocupa el lugar del predicado.
- **Solo «no» es negación.** AnCora marca `Polarity=Neg` solo en «no».
  - «Nunca sale de la casa» → «¿Sale de la casa el gato?» respondió «**Sí**», una afirmación falsa.
  - En español, «nunca», «nadie», «nada», «tampoco» o «ni» niegan antes del verbo y acompañan a «no» después del verbo («no sale nunca»). Es la concordancia negativa, y se puede medir en AnCora.
- **Sujeto omitido en plural.** G-47 resuelve solo el sujeto omitido en singular. «Los hermanos Gómez viajaron… Alquilaron una moto» → «¿Qué alquilaron los hermanos Gómez?» respondió «No lo sé», y lo mismo con «No visitaron el castillo», «Lo colocaron en la sala» y «Comieron cerca de la fuente».

**2. Potencia de la medida.** Con 64 preguntas por reserva, un mecanismo que arregla el 3 % de los casos aporta en promedio +2, dentro del ruido. Así pasó con G-49 y G-51: +1 y +24 en desarrollo, 0 en reserva.
- La regla 5.9 manda descartar lo que no sobrevive a la reserva, pero la reserva no tenía potencia para verlo.
- Esta vez la reserva es **cuádruple** (cuatro mitades con el encargo fijo, unas 128 preguntas) y hay **dos conjuntos de referencias**.
- **G-49 y G-51 se vuelven a someter a esta reserva, con sus ablaciones.** Si su aporte es ≤ 0, se retiran del motor.

## Cambio (5.8)

**1. Hueco en el predicado** (interruptor `predicate_gap`).
- La pregunta tiene el hueco en el predicado cuando el núcleo de su frase interrogativa lleva una cópula («¿De **qué color** es…?», «¿**Qué** es…?», «¿De **qué raza** es…?»).
- Entonces, en cada frase recordada donde las palabras de la pregunta quedan colocadas (G-47), es candidato el predicado con cópula cuyo sujeto es una palabra colocada, y que no está colocado él mismo.
- La respuesta es el predicado con sus dependientes, sin:
  - la cópula, el sujeto ni la puntuación;
  - los elementos coordinados;
  - los subárboles que contienen palabras colocadas.
- Compite con los demás candidatos con la clave de G-47, en el primer lugar de su colocación (distancia espejo 0).

**2. Negación concordante aprendida** (interruptor `negative_concord`). Al consolidar la sintaxis, una palabra es negadora si cumple las tres condiciones:
- aparece colgada de un verbo, después de él, con un negador marcado (`Polarity=Neg`) colgado del mismo verbo en al menos el **50 %** de al menos **5** casos;
- antes del verbo, lleva un negador marcado en a lo sumo el **5 %** de al menos **10** casos;
- su clase es adverbio, pronombre, determinante o conjunción.

La polaridad de una frase o una pregunta pasa de la paridad del número de negadores (G-41) a su presencia: con concordancia, dos negadores no afirman («no sale nunca»).

**3. Sujeto omitido en plural** (interruptor `plural_subjects`).
- Un verbo finito de 3.ª persona del plural sin sujeto, que no es impersonal aprendido (G-47), toma como sujeto la mención plural más prominente de las frases anteriores. Si no hay frases anteriores, no hay sujeto.
- Una mención plural es un sustantivo con `Number=Plur` aprendido, o una coordinación («Pedro y Luis»).
- La copia de G-47 incluye entonces los elementos coordinados.

5.8:
- **Qué fallo resuelve:** los tres de arriba, medidos en reservas gastadas.
- **Por qué no bastan los actuales:**
  - G-42 nunca propone un predicado como respuesta;
  - G-41 solo aprende de la marca `Polarity=Neg`;
  - G-47 excluyó el plural.
- **Qué lo distingue:** las tres ablaciones, las tres juntas, y las de G-49 y G-51.
- **Qué se elimina:** la paridad de negadores. G-49 y G-51, si no aportan en esta reserva.

## Evaluación

- **Desarrollo:** los 18 conjuntos gastados (791 preguntas).
- **Después de `freeze-G-52`**, con los encargos de siempre:
  - **reserva cuádruple** (cuatro mitades, cada una validada por otro subagente);
  - **dos conjuntos de referencias** nuevos.
- **Lectura:** **2400** casos nuevos de SQuAD-es `dev`, excluidos los de G-47b, G-49 y G-51, con la semilla de `freeze-G-52`. Con 600 casos, el error típico de la diferencia con el lector (~0,007) superaba la tolerancia.
- **Se miden:**
  - G-52, `estable-G-12` y el subagente;
  - cada ablación nueva y las tres juntas;
  - sin `entities` (G-51), sin `relative_resolution` y `phrase_contrast` juntas (G-49);
  - sin memoria, barajada, renombrado y reinicio.
- **Controles no aplicables, con su justificación:**
  - **contraevidencia:** la memoria literal no retira lo dicho (G-41);
  - **señal confundida:** no hay una señal auxiliar que se aprenda junto con la útil.

## Puerta

| Criterio | Umbral |
|---|---|
| Aciertos en la reserva cuádruple | ≥ `estable-G-12` + 4 |
| Aporte de G-52 (G-52 − sus tres ablaciones juntas), en la reserva y las referencias juntas | ≥ +4 |
| Afirma lo falso | ≤ 4 en la reserva, ≤ 2 en las referencias |
| Respuestas abiertas equivocadas | ≤ 15 % de las abiertas, en cada conjunto |
| Reinicio | respuestas idénticas en el 100 % |
| Memoria barajada | 0 aciertos en abiertas y sí/no |
| Renombrado | ≥ 90 % en cada conjunto |
| SQuAD-es `dev` (2400 nuevos) | F1 ≥ lector de G-28 solo − 0,005 |
| Negadores aprendidos | incluyen «no» y «nunca» |
| Regresión completa, latencia intercalada con `estable-G-12`, p95 en conversación ≤ 200 ms | como en G-46 |

**Retirada de G-49 y G-51 (5.9), en la reserva y las referencias juntas:**
- G-51 se retira si su aporte (G-52 − sin `entities`) es ≤ 0.
- G-49 se retira si su aporte (G-52 − sin relativos ni contraste por frase) es ≤ 0. Sus preposiciones aprendidas se quedan, porque sustituyen conocimiento programado.

Si pasa: verificación independiente 5.10 y `estable-G-13`. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Tres arreglos generales. El primero: cuando alguien pregunta «¿De qué color es el coche?» y le dijeron «el coche es azul», Leobot no sabía que la respuesta es justo lo que se dice del coche. El segundo: solo entendía «no» como negación; ahora aprenderá, del libro de gramática, que «nunca», «nadie» o «tampoco» también niegan, y dejará de contestar «sí» cuando le dijeron «nunca sale». El tercero: si le dicen «Los hermanos viajaron. Alquilaron una moto», entenderá que la moto la alquilaron los hermanos. Esta vez el examen será el doble de largo, para que las mejoras pequeñas se puedan ver de verdad. Y lo que no ayude se quita.
