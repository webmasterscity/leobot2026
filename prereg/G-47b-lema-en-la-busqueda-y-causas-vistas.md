# G-47b — buscar por lema y corregir las causas vistas en G-47

Fecha: 2026-09-24. Preregistro previo al código. Base: `freeze-G-47` (árbol `43dcbddd`).

## Fallo medido

[G-47](G-47-referencias-y-mismo-hecho.md) no pasó su puerta:
- **reserva doble:** 39/65, cuando el umbral era 40 (`estable-G-11` 37; subagente 65);
- **claves «no»:** 1/4.

En las referencias subió de 7 a 13/24 (subagente 22). En los conjuntos ya gastados hay siete causas generales:

1. **La búsqueda no usa lemas.** Las oraciones candidatas se buscan por la raíz de 5 letras, aunque desde G-44b la alineación compara lemas. «¿Quién dijo…?» no encuentra «Lucía dice que…».
2. **Un solo lema por forma.** AnCora anota «llamado» 20 veces como «llamado» y 8 como «llamar». Con el lema mayoritario, «¿Cómo se llama el perro…?» no alinea con «un perro llamado Rocko».
3. **Contracciones partidas.** La respuesta se arma con las palabras sintácticas: «Ríos de el Sur» en lugar de «Ríos del Sur».
4. **El posesivo de un atributo.** En «Consuelo es su esposa», el «su» se resolvió como Consuelo, el sujeto de su cláusula. El poseedor de un sustantivo atribuido con «ser» no es su sujeto.
5. **El género de un nombre.** Un nombre propio no tiene género aprendido. En «Ella compró naranjas. Él compró café.», los dos pronombres se resolvieron como Elena.
6. **«No» falso por contraste.** «¿Hay cajas de clavos en la bodega?» → «No», por «hay catorce cajas de tornillos». El valor es un complemento de lo que hay, y lo que hay no es único. G-46 ya excluía el objeto mismo, pero no sus complementos.
7. **El sustantivo de la pregunta.** En «¿De qué color es la bicicleta que compró Beatriz?», la oración que repite más palabras («Beatriz compró una bicicleta usada…») le ganó a la que tiene «color» («La bicicleta es de color azul»). Respuesta: «usada por trescientos mil pesos».

## Cambio (5.8)

1. **Búsqueda por lema** (interruptor `lemma_sets`). El índice de lo recordado guarda también los lemas de cada palabra. La búsqueda de oraciones para preguntas abiertas y de sí/no usa las mismas claves que la alineación.
2. **Lemas alternativos** (mismo interruptor):
   - cada forma lleva todos los lemas con que AnCora la anotó al menos 3 veces y en al menos el 20 % de sus apariciones;
   - dos palabras alinean si comparten uno de esos lemas.
   El lema mayoritario sigue siendo la clave de la pregunta.
3. **Contracciones.** La respuesta vuelve a unir las palabras que la separación aprendida (G-35) partió («de el» → «del»). Es una corrección de presentación, sin interruptor.
4. **Posesivo de un atributo** (interruptor `g47b_structure`). Si el sustantivo poseído lleva cópula, el sujeto de esa cláusula queda fuera de los antecedentes.
5. **Género de un nombre en la conversación** (mismo interruptor). Cuando un pronombre con género se resuelve como una mención sin género conocido, esa forma toma el género del pronombre en el resto de la conversación.
6. **Contraste solo en atributos del sujeto** (mismo interruptor). No hay «no» por contraste si el valor preguntado, o la palabra de la oración que lo reemplaza, depende de un objeto nominal: lo que se tiene, lo que hay, lo que se vende.
7. **El sustantivo de la pregunta primero** (mismo interruptor). Entre las candidatas, van primero las de oraciones que contienen el sustantivo de la frase interrogativa; después cuenta la cobertura.

5.8:
- **Qué fallo resuelve:** los siete de arriba, vistos en conjuntos gastados.
- **Por qué no bastan los actuales:**
  - la búsqueda y la alineación usan claves distintas;
  - un lema por forma pierde anotaciones reales;
  - nada propaga el género de un nombre;
  - el contraste y la cobertura no distinguen el papel de la palabra.
- **Qué lo distingue:** las ablaciones `lemma_sets` y `g47b_structure`, y G-47 congelado.
- **Qué se elimina:** la búsqueda por raíz de 5 letras cuando hay lemas.

## Evaluación

- **Desarrollo:** los 12 conjuntos gastados (439 + 65 + 24 preguntas).
- **Reserva doble nueva** después de `freeze-G-47b`, con el encargo fijo.
- **Conjunto de referencias nuevo** después de `freeze-G-47b`, con el [encargo de G-47](../experiments/g47_encargo_referencias.md).
- **Lectura:** 600 casos de SQuAD-es v1.1 `dev` (10 570 preguntas, SHA-256 `969c846d…`), traducción automática del SQuAD original y nunca usada en Leobot. Se muestrean con la semilla de `freeze-G-47b`, con la base educada de siempre.
- **Se miden:**
  - G-47b, G-47 congelado, `estable-G-11` y el subagente;
  - las dos ablaciones;
  - sin memoria, barajada y renombrado.

## Puerta

| Criterio | Umbral |
|---|---|
| Aciertos en la reserva doble | ≥ `estable-G-11` + 3 y ≥ G-47 congelado |
| Aporte en la reserva doble (G-47b − ambas ablaciones juntas) | ≥ +2 |
| Referencias | ≥ 50 % y ≥ `estable-G-11` + 5 |
| Afirma lo falso | ≤ 2 en la reserva doble, ≤ 1 en referencias |
| Respuestas abiertas equivocadas | ≤ 15 % de las abiertas, en cada conjunto |
| Claves «no» en la reserva doble | ≥ 40 % |
| Memoria barajada | 0 aciertos en abiertas y sí/no |
| Renombrado | ≥ 90 % |
| SQuAD-es `dev` (600) | F1 ≥ lector de G-28 solo − 0,005 |
| Regresión completa, latencia intercalada con `estable-G-11`, p95 en conversación ≤ 200 ms | como en G-46 |

Si pasa: verificación independiente 5.10 y `estable-G-12`. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Leobot ya entiende mejor a quién se refieren «él», «ella» o «su». Pero seguía fallando por cosas pequeñas que se repiten. Buscaba las frases por las primeras letras de las palabras, y así «dijo» no encontraba «dice». No sabía que «llamado» viene de «llamar». Escribía «de el» donde se dice «del». Y si una frase decía «ella» por Elena, no aprendía que Elena es mujer. Esta vuelta corrige esas causas, cada una de forma general, y se vuelve a medir con preguntas nuevas.
