# G-49 — relativos, contraste por frase y preposiciones aprendidas

Fecha: 2026-09-24. Preregistro previo al código. Base: `estable-G-12` (árbol `20a694f4`).

## Fallo medido

Son fallos vistos en conjuntos ya gastados (reservas de G-47 y G-47b):

1. **El pronombre relativo no se resuelve.**
   - «Camila está casada con Julián, que es ingeniero» → «¿Julián es abogado?»: la clave es «no», y respondió «No lo sé». El sujeto de «es ingeniero» es «que», y nada dice que «que» es Julián.
   - Lo mismo pasa con «Mariana tiene un perro **que** se llama Rocco».
2. **El contraste compara una sola palabra.** «La biblioteca cierra a las seis de la tarde» → «¿Cierra a las nueve de la noche?»: la clave es «no», y respondió «No lo sé». El valor preguntado es una frase («las nueve de la noche»). Como difieren dos palabras (nueve/seis y noche/tarde), la regla de «todas menos una» (G-46) no se cumple.
3. **Dos preposiciones escritas a mano en el motor.** La auditoría 5.10 de `estable-G-12` encontró «a» (el complemento que dobla un clítico dativo) y «de» (al reescribir un posesivo) en `leobot/reference.py`. Son conocimiento programado.

## Cambio (5.8)

1. **Relativos** (interruptor `relative_resolution`). Un pronombre con el rasgo aprendido de AnCora `PronType=Rel` («que», «quien», «cual»):
   - que sea sujeto u objeto de una cláusula que modifica a un sustantivo (función `acl`, relativa);
   - se sustituye en la copia resuelta (G-47) por la mención de ese sustantivo, con la copia de mención de G-47.
   Es la definición gramatical de la relativa en las dependencias universales, no una lista de palabras: la palabra que se resuelve la marca su rasgo aprendido y el antecedente lo da el árbol.
2. **Contraste por frase** (interruptor `phrase_contrast`).
   - El valor preguntado es la palabra y su subárbol dentro de la pregunta, sin palabras de función.
   - Las demás palabras de ese subárbol no cuentan como palabras que deben alinearse (se excluyen de la estructura reducida).
   - Lo demás de G-46, G-46b y G-47b no cambia: misma clase, lugar de atributo, mismo papel y misma preposición del valor.
3. **Preposiciones aprendidas** (sin interruptor: sustituyen las escritas a mano; el comportamiento debe ser el mismo). Al consolidar la sintaxis se cuentan en AnCora:
   - la preposición más frecuente de los complementos nominales (`nmod`) de un sustantivo; es la que se inserta al reescribir un posesivo;
   - la preposición más frecuente de los complementos (`obl` o `iobj`) de un verbo que lleva un clítico dativo; es la que marca el doblado.
4. **Evaluador: control de reinicio** (5.4, salvedad de la auditoría). En cada conversación, el bot se guarda y se vuelve a cargar antes de cada pregunta. Las respuestas deben ser idénticas a las del bot sin reiniciar.

5.8:
- **Qué fallo resuelve:** los relativos, el contraste de frases y el conocimiento programado.
- **Por qué no bastan los actuales:**
  - G-47 solo resuelve pronombres personales, posesivos y sujetos omitidos;
  - G-46 contrasta una palabra.
- **Qué lo distingue:** las dos ablaciones; que las preposiciones aprendidas sean «de» y «a» y den las mismas respuestas en desarrollo que las escritas a mano.
- **Qué se elimina:** las dos preposiciones escritas a mano.

## Evaluación

- **Desarrollo:** los 14 conjuntos gastados (616 preguntas).
- **Reserva doble nueva** y **conjunto de referencias nuevo** después de `freeze-G-49`, con los encargos de siempre.
- **Lectura:** 600 casos nuevos de SQuAD-es `dev` (excluidos los de G-47b), con la semilla de `freeze-G-49`.
- **Se miden:**
  - G-49, `estable-G-12` y el subagente;
  - las dos ablaciones y ambas juntas;
  - sin memoria, barajada, renombrado y **reinicio**.
- **Controles no aplicables, con su justificación:**
  - **contraevidencia:** la memoria literal no retira lo dicho; lo contradictorio se informa como contradicción (G-41), que ya se mide en las claves «sin afirmar»;
  - **señal confundida:** no hay una señal auxiliar que se aprenda junto con la útil.

## Puerta

| Criterio | Umbral |
|---|---|
| Aciertos en la reserva doble | ≥ `estable-G-12` + 2 |
| Aporte (G-49 − ambas ablaciones) en la reserva doble y referencias juntas | ≥ +2 |
| Referencias | ≥ `estable-G-12` − 1 |
| Afirma lo falso | ≤ 2 en la reserva doble, ≤ 1 en referencias |
| Respuestas abiertas equivocadas | ≤ 15 % de las abiertas, en cada conjunto |
| Reinicio | respuestas idénticas en el 100 % |
| Memoria barajada | 0 aciertos en abiertas y sí/no |
| Renombrado | ≥ 90 % |
| SQuAD-es `dev` (600 nuevos) | F1 ≥ lector de G-28 solo − 0,005 |
| Preposiciones aprendidas | «de» y «a» |
| Regresión completa, latencia intercalada con `estable-G-12`, p95 en conversación ≤ 200 ms | como en G-46 |

Si pasa: verificación independiente 5.10 y `estable-G-13`. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Cuando alguien dice «Julián, **que** es ingeniero», entendemos que el ingeniero es Julián. Leobot todavía no conectaba ese «que» con Julián. Ahora lo hará, igual que ya hace con «él» o «su». También aprenderá que, si le preguntan si la biblioteca cierra «a las nueve de la noche» y le dijeron «a las seis de la tarde», la respuesta es «no», aunque cambien varias palabras a la vez. Y dos palabras que el programa tenía escritas a mano («de» y «a») las aprenderá del libro de gramática, como aprende todo lo demás.

## Enmienda antes de congelar (2026-09-24), por lo visto en desarrollo

Medida en los 14 conjuntos gastados (616 preguntas):

1. **Frase del valor.** La primera versión tomaba como frase del valor todo lo que dependía de él. Cuando el valor es el atributo de «ser»/«estar» («¿La plaza… es **pequeña**?»), eso incluía al sujeto y se perdieron 3 «no» correctos. Ahora la frase sigue solo a los modificadores (`nmod`, `amod`, `nummod`, `compound`, `flat`, `appos`); los argumentos son vecinos, no parte del valor.
2. **Preposiciones aprendidas:** AnCora da «de» para el complemento nominal y «a» para el complemento doblado por un clítico dativo, las mismas que estaban escritas a mano.
   - Las demostraciones de la prueba focal de G-47 (`tests/test_references_and_same_fact.py`) no traían ninguna frase de la que aprenderlas. Se añadieron dos: «La casa de Ana es azul» y «Le dio pan a Ana».
   - Sus aserciones no cambian, y una prueba nueva exige que se aprendan «de» y «a». La prueba no se debilita: ahora exige además que la preposición se aprenda.

| Variante (desarrollo, 616) | Aciertos | Afirma lo falso | «no» |
|---|---|---|---|
| G-49 | 458 | 5 | 43/78 |
| sin `phrase_contrast` | 457 | 4 | 42/78 |
| ambas ablaciones | 457 | 4 | 42/78 |

Los relativos no mueven el desarrollo; el contraste por frase suma 1 acierto y 1 afirmación falsa.

**Evaluación conjunta.** Por economía de reservas, G-49 se congela junto con G-50 (preregistro aparte, en respuesta a un dato de la prueba común del usuario) y se evalúa en la misma reserva doble, con sus propias ablaciones. **La puerta de G-49 no cambia.**
