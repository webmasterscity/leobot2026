# CMP-2 — deducción de varios pasos con la misma información: Leobot frente a un subagente Claude

Fecha: 2026-09-23. Preregistro previo a la corrida. Motor: `estable-G-5` (`5d775873`), congelado.

## Por qué

[CMP-1](cmp-1-leobot-frente-a-subagente.md) midió la lectura, y el subagente fue muy superior. El tablero AGI pide medir también el razonamiento deductivo con la misma información. Aquí ambos reciben **el mismo archivo de texto**, con hechos y reglas en notación formal y preguntas. Es un mapa de capacidades, no el experimento decisivo de la Fase G, y se informa junto a CMP-1, no en su lugar.

## Tarea (generada antes de ver respuestas)

**El mundo:**
- 12 familias con 6 generaciones, construidas al azar con la semilla 2024.
- Hechos `padre(a, b)`: cada persona de la generación siguiente tiene uno o dos padres de la anterior.
- Unos 400 hechos en total.
- Nombres inventados (`p0001`…).

**Reglas, en el mismo texto:**
- `abuelo(?x,?z) :- padre(?x,?y), padre(?y,?z)`
- `bisabuelo(?x,?w) :- abuelo(?x,?y), padre(?y,?w)`
- `ancestro(?x,?y) :- padre(?x,?y)`
- `ancestro(?x,?z) :- padre(?x,?y), ancestro(?y,?z)`

**Preguntas:** 40, elegidas con la semilla 2025.
- 20 de sí o no, mitad verdaderas y mitad falsas, sobre `ancestro` (distancias 1–5), `abuelo` y `bisabuelo`.
- 20 de lista: «todos los `?y` tales que `ancestro(pX, ?y)`», o `abuelo`/`bisabuelo`, con respuestas de 1 a 60 personas.

**Participantes:**
- **Leobot:** los hechos y las reglas se cargan por su interfaz formal. La respuesta es `supported` → sí; en otro caso → no. Las listas se obtienen consultando `relacion(pX, ?y)` y recogiendo las ligaduras.
- **Subagente:** un subagente nuevo de Claude, sin contexto de la sesión. Recibe el archivo y responde en JSON, sin ejecutar código, solo razonando.

## Métricas y criterio

- Exactitud de sí o no.
- Exactitud de listas: el conjunto exacto.
- F1 medio de las listas.
- Tiempo por pregunta: pared para Leobot, total informado por la herramienta para el subagente.

Se declara superior a quien supere al otro por **≥ 5 puntos** en la media de exactitud (sí o no + listas). Se informa tal cual, sin ajustar nada.

## En palabras fáciles de entender

Le damos a Leobot y a un asistente de Claude el mismo árbol genealógico, con cientos de datos, y las mismas reglas para saber quién es abuelo o antepasado de quién. Les hacemos las mismas 40 preguntas y contamos cuántas aciertan y cuánto tardan.
