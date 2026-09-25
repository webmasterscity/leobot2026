# G-55 — el «no» por lo dicho: otro valor de la misma clase aprendida, en el mismo papel

Fecha: 2026-09-25. Preregistro previo al código. Base: `freeze-G-54` (árbol `0d5eda1e`), después de su evaluación.

## Fallo medido

Es la mayor brecha con el subagente:
- desarrollo (20 conjuntos gastados): «no» **56/119**;
- reserva cuádruple de G-52: «no» 7/18;
- el subagente acierta casi todas.

Entre los 63 fallos de desarrollo, la mayoría son **otro valor de la misma clase, dicho en el mismo papel**:

| Se dijo | Se preguntó |
|---|---|
| «fue en autobús» | «¿viajó en avión?» |
| «profesor de matemáticas» | «¿profesor de historia?» |
| «vive en la ciudad de Loja» | «¿vive en Cuenca?» |
| «participaron veinte» | «¿treinta?» |
| «de color café» | «¿es blanco?» |
| «lo conduce los martes y los jueves» | «¿los lunes?» |
| «tiene un perro» | «¿tiene un gato?» |
| «trabaja como electricista» | «¿es médico?» |

El contraste de G-46 las rechaza por tres exigencias:
- **misma etiqueta:** «Loja» no es un sustantivo común, como «ciudad»;
- **lugar de atributo;**
- **exclusión de lo que se tiene, existe o se vende:** «tiene un perro».

Esas exigencias se escribieron para no decir «no» a un valor de **otra dimensión** («¿fue caro?» frente a «azul»).

Hay otros tipos que no ataca este ciclo: antónimos («cerrada los domingos» frente a «¿abre?»), excepciones («menos el domingo») y deducciones («junto con su prima» frente a «¿viajó solo?»).

## Cambio (5.8) — interruptor `kind_contrast`

**La dimensión se decide con las clases de respuesta aprendidas de G-53, no con la etiqueta.**

**1. Cuándo se contrasta.**
- La pregunta de sí o no es afirmativa y ninguna frase la apoya ni la niega.
- Hay una frase recordada donde las demás palabras de la pregunta quedan colocadas (G-47), afirmada y no subordinada.
- En esa frase, una palabra ocupa el mismo papel que el valor preguntado respecto de su vecino (`_same_role` de G-46).

**2. Misma clase aprendida.** Se contrasta si se cumple una de estas condiciones, ninguna escrita a mano:
- los dos son miembros de una misma clase cerrada de respuestas con sustantivo aprendida de SQuAD-es (G-53: «qué día», «qué color», «qué animal»…);
- los dos son números: la clase de «cuántos» es NUM en el 81 % de los casos;
- los dos son nombres propios en un lugar con la misma preposición, y en la clase de pregunta aprendida para ese hueco los nombres propios son una clase de respuesta (≥ 10 %). Se aplica a «vive en Loja» frente a «¿vive en Cuenca?».

**3. Respuesta.** «No: me contaste que…», con la frase que lo dice (voz de G-54).

**4. Lo que no cambia.**
- Si no hay una clase común, se sigue con el contraste de G-46.
- Dos valores de dimensiones distintas no se contrastan nunca («caro» frente a «azul»: «azul» es miembro de «qué color» y «caro» no).

5.8:
- **Qué fallo resuelve:** el «no» cuando se dijo otro valor de la misma dimensión.
- **Por qué no bastan los actuales:** G-46 decide la dimensión por la etiqueta y el lugar, que no separan «perro/gato» de «perro/grande».
- **Qué lo distingue:** la ablación `kind_contrast` y el control de **clases barajadas** (los miembros se reasignan al azar entre las clases de pregunta; debe perder el efecto).
- **Qué se elimina si funciona:** la exclusión de G-47b para lo que se tiene, existe o se vende, cuando la clase aprendida decide.

## Evaluación

- **Desarrollo:** los 20 conjuntos gastados.
- **Reserva nueva** después de `freeze-G-55`, con los encargos de siempre: reserva cuádruple y referencias. Las redactan subagentes nuevos con la herramienta Agent, sin ningún mensaje del usuario, y se guardan en git antes de ejecutar.
- **Se miden:**
  - G-55, `freeze-G-54` y el subagente;
  - la ablación y las clases barajadas;
  - sin memoria, barajada, renombrado y reinicio.
- **Métricas:**
  - aciertos;
  - «no» acertados;
  - afirma lo falso: incluye decir «no» donde la clave es «no lo sé». Los redactores a veces esperan «no lo sé» cuando se dijo otro valor; eso se mide aquí y no se cambia;
  - errores confiados de G-54.

## Puerta

| Criterio | Umbral |
|---|---|
| «no» acertados (reserva y referencias juntas) | ≥ `freeze-G-54` + 5 |
| Aciertos totales | ≥ `freeze-G-54` + 3 |
| Afirma lo falso | ≤ `freeze-G-54` + 2 |
| Clases barajadas | aporte ≤ la mitad del tratamiento |
| Reinicio, barajada, renombrado, SQuAD-es, latencia | como en G-54 |

Si pasa: verificación independiente 5.10 y tag estable. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Si alguien te cuenta «Camila fue en autobús» y luego te pregunta «¿Camila viajó en avión?», contestas «No, fue en autobús». Leobot decía «no lo sé», porque no sabía si «autobús» y «avión» son el mismo tipo de dato. Ahora lo sabrá por lo que aprendió contando decenas de miles de preguntas resueltas: días con días, colores con colores, números con números. Y seguirá sin mezclar cosas distintas: que un sombrero sea azul no dice nada de si fue caro.
