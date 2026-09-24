# G-43 — la clase de respuesta se aprende y el sí/no se verifica por estructura

Fecha: 2026-09-24. Preregistro previo al código. Base: `freeze-G-42` (árbol `2628854f`). Tercer diseño de conversación en la fase G.

## Fallo medido

[G-42](../results_v3/g42_reserva_hashseed0.json) sacó 23/31 en su reserva (G-41: 14; subagente: 31) y pasó todos los criterios de conversación. Falló solo el de lectura MLQA con el bot educado completo: F1 0,2058 frente a 0,2221 ([medida](../results_v3/g42_mlqa_educado_dev.json)). Las causas, vistas solo en desarrollo:

1. **La alineación no sabe qué clase de respuesta pide la pregunta.**
   - En MLQA actúa en 31 de 300 casos con calidad pareja al lector de G-28, pero elige tramos de clase equivocada («¿Con cuántos tanques…?» → «sólo»; «¿Dónde se reunió…?» → «paralelamente»).
   - 7 casos terminan en abstención por empate.
   - En conversación, «¿Cuántos hijos tiene Beatriz?» empata entre «tres» y la lista de nombres.
2. **Solo cuentan los subárboles máximos.** Cuando la respuesta está dentro de uno mayor («de la Copa Mundial de Fútbol de 2006 en Alemania» para «¿En qué año…?»), no hay candidata correcta.
3. **La distancia se mide desde la interrogativa y no desde el núcleo de su frase.** En «¿De qué color es la casa?», «qué» está un paso más lejos que «color» de las demás palabras. Por eso «azul», que está al lado de «casa», pierde contra el sujeto.
4. **Los coordinados cuelgan del primer elemento.** En «doce manzanas y cinco naranjas», «naranjas» parece un modificador de «manzanas».
5. **El sí/no se verifica con una bolsa de palabras.**
   - «Carlos es el hermano de Marta y vive en Toledo» confirma «¿Marta vive en Toledo?».
   - «Marina afirmó que la reunión es el lunes» confirma «¿La reunión es el lunes?».

## Cambio (5.8)

### 1. Clase de respuesta aprendida por conteo

- **Qué se guarda.** Cada ejemplo de lectura guarda solo el principio de la pregunta (6 palabras) y las palabras de la respuesta (hasta 4), en minúsculas. El texto no se memoriza.
- **Cuándo se compila.** Al consolidar la lectura. Así el resultado no depende del orden en que llegan la sintaxis y la lectura.
- **Qué se compila.**
  - **Clave:** la primera interrogativa aprendida de la pregunta, más el sustantivo que la sigue, si lo hay.
  - **Clase:** la etiqueta aprendida más frecuente de la primera palabra de la respuesta que no es de función.
  - **Probabilidad:** P(clase | clave) = (n + 1) / (n_clave + número de clases). Se usa la clave con sustantivo si tiene al menos 5 ejemplos; si no, solo la interrogativa.
- **Cómo se usa.** Cada candidata tiene una clase, calculada con la misma regla sobre su tramo.

### 2. Todas las candidatas

Es candidato todo subárbol sin palabras de la pregunta que tenga al menos una palabra que no sea de función. Ya no hace falta que sea máximo.

### 3. Distancia desde el núcleo

La distancia en la pregunta se mide desde el núcleo de la frase interrogativa: el sustantivo si lo hay; si no, la interrogativa.

### 4. Coordinados

En el análisis de las oraciones recordadas y de la pregunta, cada coordinado (`conj`) pasa a colgar de la cabeza de su primer elemento, con la misma función que este. Es la convención de las dependencias «mejoradas» de Universal Dependencies. Además, un coordinado verbal hereda el sujeto de su primer elemento.

### 5. Puntuación

Clave de orden:
1. número de palabras de la pregunta alineadas (mayor es mejor);
2. puntuación = espejo + (−ln P(clase | clave)) (menor es mejor);
3. preposición;
4. función sintáctica.

El empate entre textos distintos sigue siendo abstención («No lo sé con seguridad…»).

### 6. Sí/no por estructura

Una oración apoya una pregunta de sí o no si cumple tres condiciones:
- contiene todas sus raíces, como en G-41;
- **cada enlace entre dos palabras de contenido de la pregunta** (cada palabra con su ancestro de contenido más cercano) une en la oración las palabras alineadas por un camino de largo como máximo el de la pregunta + 1, sin pasar por otra palabra alineada. El camino se mide en el grafo con los coordinados del punto 4 y los sujetos heredados;
- **no está subordinada:** ni la palabra alineada más alta ni sus ancestros hasta la raíz tienen un dependiente de clase subordinante (SCONJ, aprendida). Si todo lo demás coincide pero la frase está subordinada («X afirmó que…», «si…»), la respuesta es «No lo sé con seguridad: lo que me dijeron lo presenta como algo dicho o supuesto, no como un hecho.».

La polaridad sigue la paridad de G-41.

**Interruptores de ablación:**
- `answer_classes`: sin clase de respuesta, la puntuación es solo el espejo;
- `structural_verification`: sin estructura, la verificación es la bolsa de palabras de G-41.

### 5.8

- **Qué fallo resuelve:** la caída de MLQA de G-42 y los errores de clase, coordinación y verificación vistos en desarrollo.
- **Por qué no bastan los actuales:** G-42 no tiene ninguna noción de clase de respuesta; la verificación de G-41 no mira la estructura.
- **Qué lo distingue:** las dos ablaciones; MLQA con el bot educado completo; la reserva de conversación con G-42 congelado como línea base.
- **Qué se elimina si funciona:** la regla de «solo subárboles máximos» y la verificación por bolsa de palabras cuando hay sintaxis.

Trabajos cercanos:
- la clasificación de preguntas por tipo de respuesta: Li y Roth (2002), *Learning question classifiers*;
- las dependencias mejoradas de UD: Schuster y Manning (2016), *Enhanced English Universal Dependencies*.

Aquí la clase se aprende por conteo de los ejemplos de educación, sin taxonomía escrita a mano.

## Evaluación

**Base educada:** la misma receta (AnCora `train` + 2000 MLQA), reconstruida con el motor de G-43.

**Desarrollo (visible):**
- los tres conjuntos de conversación ya usados (desarrollo de G-41, reserva de G-41 y desarrollo de G-42);
- la reserva de G-42, ya gastada;
- MLQA en desarrollo limpio con el bot educado completo.

**Reserva:** un conjunto nuevo después de `freeze-G-43`, con el mismo procedimiento, que no se mira antes de ejecutar. Se miden:
- G-43;
- G-42 congelado;
- el subagente sin claves;
- los controles de G-42 (sin memoria, barajada, renombrado);
- las dos ablaciones nuevas.

## Puerta

| Criterio | Umbral |
|---|---|
| Aciertos de G-43 en la reserva | ≥ 60 % y ≥ G-42 congelado + 2 |
| Sí o no falsos (sin contar abstenciones) | ≤ 1 |
| Respuestas abiertas equivocadas | ≤ 3 |
| Memoria barajada | 0 aciertos en abiertas y sí/no |
| Renombrado: respuestas invariantes | ≥ 90 % |
| **Lectura MLQA en desarrollo limpio, bot educado completo** | **F1 ≥ 0,2171** (0,2221 − 0,005) |
| Aporte de la clase en MLQA: G-43 − ablación `answer_classes` | ≥ +0,005 F1 |
| Regresión completa | sin fallos nuevos |
| Latencia fija intercalada | ≤ +20 % |
| Respuesta en conversación | p95 ≤ 200 ms |

La brecha con el subagente se informa sin maquillarla. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Leobot ya encuentra el hueco de una pregunta en lo que se le contó, pero a veces llena el hueco con una palabra que no es del tipo pedido. Por ejemplo, a «¿cuántos?» contesta con algo que no es un número. Ahora aprenderá, contando ejemplos, qué tipo de palabra responde a cada clase de pregunta:
- «cuántos» se responde casi siempre con un número;
- «dónde», con un nombre de lugar;
- «quién», con el nombre de una persona.

También revisará quién hace qué antes de decir «sí». Así, si «Carlos vive en Toledo», no dirá que Marta vive en Toledo. Y si alguien solo *dijo* algo («Marina afirmó que la reunión es el lunes»), no lo dará por hecho.
