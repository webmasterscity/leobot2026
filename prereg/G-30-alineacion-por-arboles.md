# G-30 — responder alineando pregunta y oración por sus árboles aprendidos

Fecha: 2026-09-23. Preregistro previo al código. Base: `freeze-G-29b` (`3b13f49b`), que une la lectura por alineación de G-28b (reserva F1 0,218–0,240, falla F1 ≥ 0,25) y la sintaxis aprendida de G-29 (clases 97,2 %, UAS 0,743).

## Fallo y causa

G-28b elige el tramo con rasgos lineales: palabras vecinas, distancia a palabras alineadas y forma. En la reserva, 99 de 200 respuestas no compartían ni una palabra con la correcta, y la [curva de educación](../results_v3/g28b_learning_curve_dev.json) muestra que más ejemplos casi no ayudan. Una persona usa la estructura: en «¿Qué libro escribió Berners-Lee?» busca en «Berners-Lee escribió *Weaving the Web* en 1999» lo que depende de «escribió» y no es Berners-Lee.

## Hipótesis y alternativa

Si la pregunta y la oración se analizan con la sintaxis aprendida (G-29) y los candidatos incluyen los subárboles completos de la oración, con rasgos estructurales aprendidos de los mismos ejemplos resueltos, sube el acierto. Rasgos estructurales:
- si el tramo es un subárbol completo;
- la clase de la palabra que lo encabeza;
- si depende de la palabra de la oración alineada con la cabeza del marcador del hueco en la pregunta;
- si contiene palabras alineadas.

Todo va condicionado al marcador aprendido, como en G-28b. Alternativa: los errores del analizador (UAS 0,74) anulan la ganancia, o los rasgos lineales ya contenían esa información.

5.8: resuelve la elección de tramo; los actuales no bastan (curva plana); la ablación estructural lo distingue; si funciona, reemplazaría los rasgos de vecindad lineal que resulten redundantes (medido por ablación).

## Datos, controles y puerta

Los mismos de G-28b:
- educación: 2000 ejemplos MLQA de `test`, semilla 2828, más la educación sintáctica completa de G-29 (UD AnCora `train`);
- desarrollo visible: 300 casos de `test` sin párrafos compartidos con la educación;
- reserva: 200 de `dev`, sin los 20 del tablero, con la semilla de `freeze-G-30:leobot`.

Controles:
- los mismos de G-28b;
- **ablación estructural**: mismo motor y educación, sin rasgos de árbol;
- **sintaxis barajada**: educación sintáctica con cabezas barajadas.

Puerta, con hashseed 0 y 1 y salidas idénticas:

| Criterio | Umbral |
|---|---|
| F1 | ≥ 0,25 |
| Exactas | ≥ 0,10 |
| Ventaja sobre la ablación estructural | ≥ 0,02 F1 |
| Ventaja sobre la sintaxis barajada | ≥ 0,02 F1 |
| Honestidad | ≥ 90 % |
| Sin hueco | ≥ 95 % |
| Fresco | 0 respuestas |
| Renombrado | a ≤ 0,03 del tratamiento |
| Reinicio | idéntico |
| Memoria conjunta | ≥ 0,8 × tratamiento |
| Latencia de respuesta p95 | ≤ 10 ms (el análisis de oraciones ocurre al leer, no al responder) y ≤ 200 ms con memoria conjunta |
| Lectura | ≤ 100 ms p95 por oración |
| Educación | ≤ 240 s de CPU |
| RSS | ≤ 512 MiB |

Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Leobot ya sabe marcar, en una frase nueva, qué palabra depende de cuál. Ahora usará eso para leer. Cuando le pregunten «¿qué libro escribió Berners-Lee?», buscará en el texto lo que cuelga de «escribió» y no es Berners-Lee, en vez de fijarse solo en qué palabras están cerca.
