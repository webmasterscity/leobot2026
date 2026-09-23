# G-32 — puntuar arcos por respaldo jerárquico en vez de sumar rasgos correlacionados

Fecha: 2026-09-23. Preregistro previo al cambio del motor. Base: `freeze-G-31` (`7d68100c`). Último estable: `estable-G-3`.

## Fallo y causa

G-31 falló solo por el F1 de sujeto: 0,590 frente a 0,60. En desarrollo, la mayoría de los errores de sujeto venían de cabezas equivocadas.

El puntaje de arco de G-29 **suma** log-razones de cuatro rasgos que comparten clases y dirección. Así cuenta varias veces la misma evidencia, el mismo defecto que hizo fracasar a G-30 en la lectura. En cambio, las funciones de G-31, combinadas por **respaldo jerárquico** (cada contexto suavizado hacia el más general), aciertan el 94 % cuando la cabeza es correcta.

**Exploración ya hecha, que se declara:** con un parche de prueba fuera del motor, en el desarrollo visible (300 oraciones de `dev`), el respaldo jerárquico dio:

| Combinación | UAS | LAS | F1 de sujeto |
|---|---|---|---|
| Suma de rasgos (actual) | 0,737 | 0,693 | 0,578 |
| Respaldo jerárquico, κ=5 | 0,765 | 0,715 | 0,616 |

Se probaron κ = 1, 2, 5, 10 y 20, y dos órdenes léxicos. Se eligió κ=5 con el orden cabeza→dependiente. La reserva `test` no se tocó.

## Hipótesis y alternativa

El rasgo del arco se estima por una cadena de contextos, de lo general a lo específico:
1. (clase de la cabeza, clase del dependiente, dirección);
2. + distancia;
3. + verbo o puntuación entre ellos, y si hay otra palabra de la clase del dependiente entre ellos;
4. + palabra cabeza, si se vio ≥3 veces;
5. + palabra dependiente, si se vio ≥3 veces.

Cada nivel se suaviza hacia el anterior: tasa = (arcos + κ·tasa previa)/(oportunidades + κ), con κ=5. El puntaje del arco es la log-razón de la tasa final frente a la tasa base. Esto mejora las cabezas y, con ellas, las funciones.

Alternativa: la ganancia de desarrollo no se sostiene en una reserva nueva.

5.8:
- **Qué reemplaza:** la suma de rasgos del puntaje de arco.
- **Qué se elimina:** los rasgos sumados b, c y d.

## Datos, controles y puerta

Los mismos de G-29 y G-31: educación con UD AnCora `train`; reserva de 300 oraciones de `test` de ≤60 palabras, elegidas con la semilla de `git rev-parse freeze-G-32:leobot`.

Controles, los de G-31 y además:
- **motor de `freeze-G-31` en proceso hijo**, sobre la misma reserva, como línea base de la suma;
- **etiquetas y cabezas barajadas.**

| Criterio | Umbral |
|---|---|
| Clases | ≥ 0,92 |
| UAS | ≥ 0,75 |
| Ventaja de UAS sobre `freeze-G-31` en la misma reserva | ≥ 0,01 |
| LAS | ≥ 0,70 |
| F1 de sujeto | ≥ 0,60 |
| F1 de objeto | ≥ 0,60 |
| Función correcta con cabeza correcta | ≥ 0,85 |
| Ventaja sobre la ablación sin léxico ni marcador | ≥ 0,02 |
| LAS con etiquetas barajadas | ≤ 0,40 |
| UAS con cabezas barajadas | ≤ 0,35 |
| Fresco | sin análisis |
| Reinicio | idéntico |
| p95 por oración de ≤40 palabras | ≤ 100 ms |
| Educación | ≤ 240 s de CPU |
| RSS | ≤ 768 MiB |
| Hashseed 0 y 1 | idénticos |
| Huella | idéntica |

Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Leobot decidía de qué palabra depende cada una sumando varias pistas. Varias de esas pistas decían casi lo mismo, así que contaba dos o tres veces la misma señal. Ahora va a mirar primero la pista más general y después afinarla con las más específicas, sin repetir lo mismo. En una prueba preliminar, eso mejoró los resultados. Ahora hay que confirmarlo con oraciones que nunca vio.
