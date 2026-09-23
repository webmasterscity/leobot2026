# G-34 — ¿es la paráfrasis un «no sabía»? Educación léxica con un diccionario abierto

Fecha: 2026-09-23. Preregistro previo al código. Base: el motor candidato `freeze-G-32c`: lectura de G-28b, más la sintaxis y las funciones de G-32c.

## Pregunta y causa

G-28b, G-30 y G-33 coinciden: la pregunta usa palabras distintas de las del texto para lo mismo («ganar» y «vencer», «morir» y «fallecer»), y la alineación no las une. La [curva de educación](../results_v3/g28b_learning_curve_dev.json) muestra que más ejemplos de preguntas no lo arreglan. Queda por comprobar si el fallo es en parte un **«no sabía»**, es decir, falta de conocimiento léxico. Una persona trae ese conocimiento de antes; a Leobot se le puede **enseñar como datos**, sin ningún mecanismo que invente sinónimos.

## Fuente

WordNet español del Multilingual Central Repository 3.0, empaquetado en Open Multilingual Wordnet:
- repositorio `omwn/omw-data`, revisión `406bf83b3c507a3d1f26e88252d5d66893fd36bf`;
- archivo `wns/mcr/wn-data-spa.tab`, SHA-256 `0ec37ce94ee2acc63ad6b120e1051f9841d172778cc24adc0023fb8dccf0a7cd`, 166 282 líneas;
- licencia CC BY 3.0. Citas: Gonzalez-Agirre, Laparra y Rigau (2012); Bond y Foster (2013).

Se usan solo los pares (sentido, lema). No se usan relaciones entre sentidos ni el inglés.

## Mecanismo (5.8)

Nueva demostración: `observe_lexical_entry(sentido, lema)`.

Al leer:
- una palabra de la pregunta que no aparece literalmente cuenta como presente, con un peso de 0,5, si una palabra de la oración comparte con ella algún sentido enseñado;
- la comparación usa la raíz de 5 letras de G-28;
- esa presencia cuenta para puntuar el pasaje (BM25) y la oración;
- el **umbral de abstención sigue siendo literal**, porque se calibró así.

5.8:
- **Qué fallo resuelve:** la paráfrasis léxica.
- **Por qué no bastan los actuales:** la alineación exige la misma raíz, y IBM-1 no aprendió nada con 2000 ejemplos.
- **Qué lo distingue:** sin diccionario frente a diccionario barajado.
- **Qué eliminaría:** el parámetro retirado `use_correspondences`, que el sentido léxico reemplazaría.

## Datos, controles y puerta

Lectura: igual que G-28b.
- Educación: 2000 ejemplos de MLQA `test`, semilla 2828, más el diccionario y la sintaxis de G-32c.
- Desarrollo visible limpio: 300 casos.
- Reserva: 200 casos de `dev`, sin los 20 del tablero, con la semilla de `freeze-G-34`.

Controles:
- **Sin diccionario:** mismo motor.
- **Diccionario barajado:** los mismos lemas repartidos al azar entre sentidos, conservando cuántos lemas tiene cada sentido.
- Los de G-28b: fresco, honestidad, sin hueco, renombrado, reinicio y memoria conjunta.

Puerta, con hashseed 0 y 1:

| Criterio | Umbral |
|---|---|
| F1 | ≥ 0,25 |
| Exactas | ≥ 0,10 |
| Ventaja sobre el mismo motor sin diccionario | ≥ 0,01 F1 |
| Diccionario barajado | ≤ sin diccionario + 0,005 |
| Honestidad | ≥ 90 % |
| Sin hueco | ≥ 95 % |
| Fresco | 0 respuestas |
| Renombrado | a ≤ 0,03 |
| Reinicio | idéntico |
| Memoria conjunta | ≥ 0,8 × tratamiento |
| Latencia de respuesta p95 | ≤ 10 ms y ≤ 200 ms |
| Educación | ≤ 300 s |
| RSS | ≤ 768 MiB por proceso |

Si la ventaja aparece pero F1 no llega a 0,25, se registra como «no sabía» parcial: la información ayuda, pero no alcanza. Si no aparece ventaja, la paráfrasis léxica no es el límite y el fallo sigue siendo «no pudo». Nada se relaja.

## En palabras fáciles de entender

Leobot no sabe que «fallecer» y «morir» significan lo mismo. Le daremos un diccionario público de palabras con igual significado, sin decirle las respuestas del examen, y veremos si así encuentra mejor las respuestas. Si mejora, parte de lo que le faltaba era conocimiento, y eso se arregla enseñándole más. Si no mejora, le falta otra capacidad.
