# G-36 — comprobar contradicciones solo donde algún hecho o regla puede establecerlas

Fecha: 2026-09-23. **Declaración:** la corrección se implementó antes de este preregistro. La descubrió [CMP-2](cmp-2-deduccion-con-la-misma-informacion.md): con el motor `estable-G-5`, 3 de las 20 preguntas de lista quedaron «incompletas».

## Fallo y causa

`Engine.answer` revisa las contradicciones de cada átomo de cada prueba lanzando una consulta de su opuesto, con un tope de 64. En consultas con muchas respuestas de pruebas profundas (por ejemplo, 23 ancestros), el tope se agota y la respuesta se marca `incomplete`, aunque la base **no tenga ningún conocimiento negativo** que pudiera contradecirla.

## Cambio

Antes de consultar el opuesto de un átomo, se comprueba en los índices si existe algún hecho con el predicado opuesto o alguna regla cuya cabeza sea ese predicado. Si no existe, el opuesto no puede derivarse y la consulta se omite, sin gastar el tope. La respuesta es exactamente la misma; solo desaparecen las comprobaciones imposibles.

Prueba focal nueva: `tests/test_conflict_checks_scale.py`.
- 40 respuestas sin conocimiento negativo deben dar `bindings`.
- Una negación explícita debe seguir detectándose.
- Sin la corrección, la prueba falla.

## Confirmación (CMP-2b)

Se genera un mundo **nuevo** con el mismo generador de CMP-2, con estas semillas tomadas de `git rev-parse freeze-G-36:leobot`:
- mundo: los primeros 8 hexadecimales;
- preguntas: los 8 siguientes.

Participantes:
- el motor congelado;
- el motor `estable-G-5`, en proceso hijo;
- un subagente Claude nuevo, sin contexto, que no ejecuta código.

Puerta:

| Criterio | Umbral |
|---|---|
| Exactitud media del motor congelado | 1,0 |
| Respuestas `incomplete` | 0 |
| Regresión completa | sin fallos nuevos |
| Latencia fija | ningún p95 empeora más de 20 % frente a `estable-G-5` |

Se informa la exactitud del subagente y la de `estable-G-5` en el mismo mundo.

## En palabras fáciles de entender

Leobot revisaba si alguna de sus conclusiones podía estar contradicha, pero lo hacía incluso donde era imposible que hubiera una contradicción, y con muchas respuestas se quedaba sin tiempo y decía «no terminé». Ahora solo revisa donde de verdad podría haber una contradicción. Lo comprobaremos con un árbol genealógico nuevo que nadie ha visto.
