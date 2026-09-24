# G-39d — no responder cuando el conjunto de soluciones mínimas puede estar incompleto

Fecha: 2026-09-24. Preregistro previo al cambio. Base: `estable-G-10` (`bcdbc28f`).

## Fallo (auditoría 5.10 de G-39c)

`predict_grid` responde aunque la búsqueda haya quedado incompleta. La inversión de `at` puede encontrar una solución de tamaño 7 antes de que se complete el tamaño 5. Si después se agota el presupuesto, queda un conjunto «mínimo» parcial. Un programa más pequeño, o uno del mismo tamaño que discrepe, no se llegó a ver, y la ambigüedad no se detecta.

Caso mínimo de la auditoría: recortar la cuadrícula (`out[r][c] = in[r+1][c+1]`), semilla 9, con 1500 candidatos. Da `hypothesis` con 1 programa; con la búsqueda completa hay 2 que discrepan y la respuesta es `ambiguous`.

## Cambio

`fit` informa `minimal_complete`: es verdadero si todos los tamaños menores que el de la solución ganadora se enumeraron completos. `predict_grid` responde `incomplete`, es decir se abstiene, si el alto, el ancho o la celda tienen `minimal_complete` falso.

Nada más cambia. Las búsquedas y las soluciones son las mismas; solo cambia cuándo se responde.

## Pruebas y puerta

**Prueba focal:** el caso de la auditoría con 1500 candidatos da `incomplete`; con la búsqueda completa sigue `ambiguous`.

**ARC, sobre `training` (desarrollo, solo tratamiento):**
- los errores no aumentan frente a G-39c (1);
- se informan los aciertos que se pierden por abstenerse.

**Reserva:** no hay reserva nueva de ARC. El cambio solo reduce respuestas, y el desgaste de `evaluation` desaconseja gastarla en esto.

**Además:**
- regresión completa sin fallos nuevos;
- latencia fija intercalada con `estable-G-10`, ≤ +20 %.

## En palabras fáciles de entender

Si Leobot se queda sin tiempo antes de revisar todas las reglas más simples, ya no dará su respuesta como segura: dirá que no terminó de buscar.
