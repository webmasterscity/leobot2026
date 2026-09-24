# G-46b — el contraste exige el mismo papel

Fecha: 2026-09-24. Preregistro previo al código. Base: `freeze-G-46` (árbol `bc657715`).

## Fallo medido

[G-46](../results_v3/g46_reserva_hashseed0.json) llevó los «no» de 0/10 a 9/10 y sacó 49/62 (`estable-G-11`: 40; subagente: 59). No pasó la puerta por 3 afirmaciones falsas; el tope era 2:
- **1 nueva:** «¿Marta es enfermera?» → «No» por «Diego es el hermano de Marta». En la pregunta, «Marta» es el sujeto del atributo. En la oración es complemento de «hermano», cuyo sujeto es Diego. G-46 exigía la misma casilla (etiqueta, preposición, lugar de atributo), pero no el mismo papel de la palabra vecina.
- **2 previas** de `estable-G-11`: «Según Marta, la reunión es el jueves» → «Sí». La atribución con «según» no se reconoce como dicho por otro. Es un límite léxico que **no se ataca aquí**; queda como riesgo medido.

## Cambio

**El mismo papel.** Sea `n` la palabra de la pregunta enlazada con el valor `v`. En la oración, la palabra que contrasta, `w`, debe relacionarse con la palabra alineada a `n` igual que `v` se relaciona con `n`:
- con la misma dirección, es decir, quién depende de quién en el árbol mejorado, sin contar palabras de función;
- y con la misma función sintáctica.

La única equivalencia admitida es la de predicativo y atributivo: un adjetivo predicado de `n` con verbo copulativo («el carro es azul») equivale a un adjetivo que modifica a `n` («un carro azul»). Es una equivalencia gramatical general del español, no una lista de palabras.

Lo demás de G-46 no cambia. Interruptor: `contrast_answers` (como en G-46).

## Evaluación

- **Desarrollo:** los 9 conjuntos gastados (incluida la reserva doble de G-46, 376 preguntas).
- **Reserva doble nueva** después de `freeze-G-46b`, con el mismo procedimiento.
- **MLQA:** 600 casos no vistos, excluida también la muestra de G-46, con la semilla de `freeze-G-46b`.
- Se miden G-46b, `estable-G-11`, el subagente, la ablación, sin memoria, barajada y renombrado.

## Puerta

Es la misma que la de G-46:

| Criterio | Umbral |
|---|---|
| Aciertos en la reserva doble | ≥ `estable-G-11` + 3 |
| Claves «no» acertadas | ≥ 40 % |
| Aporte (G-46b − ablación) | ≥ +3 |
| Afirma lo falso | ≤ 2 |
| Respuestas abiertas equivocadas | ≤ 15 % |
| Memoria barajada | 0 aciertos en abiertas y sí/no |
| Renombrado | ≥ 90 % |
| MLQA no vista (600) | F1 ≥ lector de G-28 solo − 0,005 |
| Regresión, latencia intercalada con `estable-G-11`, p95 ≤ 200 ms | como en G-46 |

Si pasa: verificación independiente 5.10 y `estable-G-12`. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Leobot ya dice «no» cuando le preguntan por otro color o por otra hora que la que le dijeron. Pero una vez se confundió. Le habían dicho «Diego es el hermano de Marta», le preguntaron «¿Marta es enfermera?» y contestó «no», como si «hermano» fuera lo que Marta es. Ahora revisará que la palabra ocupe el mismo papel: en la pregunta, Marta es de quien se dice algo; en esa frase, no lo es.
