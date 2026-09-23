# G-33 — convertir lo leído en eventos estructurados y las preguntas en consultas

Fecha: 2026-09-23. Preregistro previo al código. Base: `freeze-G-32c`, que tiene la sintaxis aprendida (UAS 0,768; LAS 0,722) y la lectura por alineación de G-28b (MLQA F1 0,218–0,240).

## Fallo y causa

G-28b satura (curva plana) y G-30 mostró que sumar rasgos de árbol al elegidor de tramos empeora. Una persona que lee «Berners-Lee escribió *Weaving the Web* en 1999» guarda algo como «escribir: quién = Berners-Lee; qué = *Weaving the Web*; cuándo = 1999». Ante «¿Qué libro escribió Berners-Lee?», busca el evento «escribir» cuyo «quién» es Berners-Lee y responde con su «qué». Leobot tiene memoria de hechos y consultas, pero no convierte oraciones leídas en esa forma.

## Hipótesis

Al leer, cada palabra cabeza del análisis aprendido forma un **evento** con sus dependientes: función aprendida y texto del subárbol, con la raíz de 5 letras de cada palabra. Se guarda con fuente y oración.

Para responder:
1. Se analiza la pregunta.
2. El marcador del hueco se identifica como en G-28b.
3. Se sube por los ancestros del marcador hasta la palabra que ancla la pregunta.
4. Se buscan eventos cuya cabeza coincide con esa palabra y cuyos otros dependientes coinciden en función y cabeza con los de la pregunta.
5. La respuesta es el subárbol del evento que ocupa la **función** que el marcador (o su frase) cumple en la pregunta.

Si ningún evento coincide sin ambigüedad, se usa la lectura por alineación de G-28b sin cambios. La respuesta se marca como `literal` con la fuente y dice por qué vía se obtuvo.

Los nombres de funciones y clases son símbolos del esquema de anotación que se enseñó; el código **no** los lista. La coincidencia usa igualdad de símbolos aprendidos, no reglas por función.

Alternativa: la precisión de los eventos, limitada por el LAS de 0,72 y las paráfrasis, deja la cobertura estructural tan baja que el total no mejora.

5.8:
- **Qué fallo resuelve:** la lectura no usa estructura.
- **Por qué no bastan los actuales:** el elegidor de tramos no aprovecha los árboles.
- **Qué lo distingue:** la ablación sin eventos, con el mismo motor.
- **Qué eliminaría si funciona:** la vía de alineación quedaría solo como respaldo.

## Datos, controles y puerta

Los de G-28b/G-30:
- educación: 2000 ejemplos MLQA, más la educación sintáctica de UD AnCora `train` con funciones;
- desarrollo visible limpio: 300 casos;
- reserva: 200 casos de `dev`, sin los 20 del tablero, con la semilla de `freeze-G-33`.

Controles:
- **ablación sin eventos:** solo alineación;
- **sintaxis barajada:** funciones barajadas en la educación sintáctica;
- los de G-28b: fresco, honestidad, sin hueco, renombrado, reinicio, memoria conjunta.

Se informan la cobertura y la precisión de la vía estructural por separado.

Puerta, con hashseed 0 y 1:

| Criterio | Umbral |
|---|---|
| F1 total | ≥ 0,25 |
| Exactas | ≥ 0,10 |
| Ventaja sobre la ablación sin eventos | ≥ 0,02 F1 |
| Precisión exacta de la vía estructural | ≥ la de la alineación en los mismos casos |
| Honestidad | ≥ 90 % |
| Sin hueco | ≥ 95 % |
| Fresco | 0 respuestas |
| Renombrado | a ≤ 0,03 del tratamiento |
| Reinicio | idéntico |
| Memoria conjunta | ≥ 0,8 × tratamiento |
| Latencia de respuesta p95 | ≤ 10 ms y ≤ 200 ms con memoria conjunta |
| Lectura por oración p95 | ≤ 100 ms |
| Educación | ≤ 300 s |
| RSS | ≤ 768 MiB por proceso |

Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Cuando Leobot lea una frase, anotará quién hizo qué, a quién, cuándo y dónde, como en una ficha. Cuando le pregunten, buscará la ficha que corresponde y responderá con el dato que falta. Si no encuentra una ficha clara, usará el método anterior y, si tampoco sirve, dirá que no sabe.
