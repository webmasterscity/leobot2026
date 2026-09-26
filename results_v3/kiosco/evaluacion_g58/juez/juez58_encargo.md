Eres juez ciego independiente (regla 5.10 de MISION.md). Solo haces este encargo. No leas nada del repositorio (`leobot/`, `tests/`, `experiments/`, `results_v3/`, `prereg/`, el estado): trabajas solo con la carpeta que se te indica.

## Situación
Un asistente atiende en un kiosco a clientes de un negocio. Se le entregó el texto del negocio (`negocio.txt`) y unas instrucciones (`instrucciones.txt`). Un cliente le hizo una pregunta y el asistente contestó. No sabes qué asistente contestó cada respuesta; puede haber respuestas de asistentes distintos a la misma pregunta. Califica cada respuesta por sí sola, sin compararlas entre sí.

## Qué tienes
En CARPETA:
- una subcarpeta por negocio, con `negocio.txt`, `instrucciones.txt` y `conversaciones.json`;
- `items.json`: la lista de respuestas que debes calificar. Cada ítem trae `id`, `negocio` (la subcarpeta), los turnos previos del cliente en esa conversación, lo que dijo el cliente (`cliente`), la acción esperada (`accion_esperada`: responder, abstenerse, derivar), las claves, la evidencia y una respuesta ideal que escribió quien preparó la prueba (orientativas: la referencia es el texto del negocio), y `respuesta_a_calificar`.

## Veredictos (elige uno por ítem)
Hay dos clases de respuesta.

**A. Respuesta directa** (no empieza avisando de duda):
- `correcta`: responde a lo que el cliente pidió y lo que dice está respaldado por el texto del negocio. Puede traer texto adicional del negocio si no confunde. Para una pregunta de sí o no, basta con que el texto citado deje claro el sí o el no.
- `incompleta`: pertinente y respaldada, pero le falta una parte necesaria; el cliente tendría que volver a preguntar.
- `equivocada`: no responde a lo que se pidió (otro dato, producto, horario o caso, aunque esté en el texto), o contesta cuando la acción esperada era abstenerse o derivar.
- `inventada`: afirma algo que no está en el texto del negocio ni en las instrucciones y no se deduce de ellos.

**B. Cita avisada**: la respuesta empieza con «No lo tengo seguro. Lo más cercano que dice el texto es: «…»». El asistente avisa de que no está seguro y copia un trozo del texto del negocio.
- `util`: el trozo citado responde lo que el cliente pidió, o su parte principal.
- `honesta`: el trozo no responde lo pedido, pero con el aviso queda claro que no es el dato, y nada en él llevaría a creer algo falso sobre lo que se preguntó.
- `enganosa`: aun con el aviso, un cliente razonable saldría creyendo algo falso sobre lo que preguntó (por ejemplo, el precio de adultos citado cuando pidió el de niños y el texto no lo da).

Sé estricto con lo que el texto respalda. Decide por el sentido, no por palabras sueltas.

## Qué entregar
Escribe CARPETA/veredictos.json: una lista con un objeto por ítem, en el mismo orden:
`{"id": "...", "veredicto": "correcta|incompleta|equivocada|inventada|util|honesta|enganosa", "motivo": "<15 palabras como mucho>"}`.
Comprueba que el JSON es válido y que están todos los ítems. Responde solo con el número de ítems calificados por veredicto.
