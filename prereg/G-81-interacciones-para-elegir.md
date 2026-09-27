# G-81 · Combinaciones aprendidas para elegir la frase

2026-09-27. Preregistro antes de código o resultados. Desarrollo gastado.

## En palabras fáciles de entender

Una pista puede ayudar solo cuando aparece junto con otra. Por ejemplo, el
aprendiz podría descubrir que cierta combinación es más fiable que cada parte
por separado. Probaremos si aprender esas combinaciones permite elegir mejor
entre las frases del texto. El desarrollador no decidirá qué combinaciones
sirven: se aprenderán de los mismos ejemplos. La prueba mantendrá el límite
para citar y comprobará tanto los aciertos como las citas cuando falta el dato.

## Hipótesis y diferencia comprobable

G-68 ya tiene un aprendiz de árboles, pero lo probó para decidir si citar la
primera candidata, con siete rasgos. PAR-2/G-79 eligen entre seis candidatas
sumando el aporte de 25 rasgos. Falta probar **interacciones aprendidas de esos
25 rasgos antes de elegir**, con el mismo conjunto de candidatas y etiquetas.
No atribuir novedad al algoritmo de árboles ni añadir otro aprendiz.

La fuente clásica [Breiman, informe de 1994](https://www.stat.berkeley.edu/~breiman/bagging.pdf)
describe el promedio de predicciones enseñadas con muestras repetidas y sus
límites: puede reducir variación en árboles, pero no garantiza mejorar un
predictor ni remedia información insuficiente. Sus datos no son conversaciones.
La revisión de 2026 ya registrada motivó G-80; no sustituye este control local.
Reutilizar el código de G-68 permite probar la hipótesis sin introducir otro
subsistema o un método neuronal.

## Datos y aprendizaje fijos

- Base, referencia PAR-2 y educación G-78 de G-79. Verificar sus SHA existentes.
  Mismos 3 520 turnos TRAIN, 20 629 candidatas y mitades por negocio.
- Llamar directamente a `g68.fit`/`predict`: 15 árboles, profundidad máxima 6,
  mínimo 40 filas para intentar partir y 20 por rama, mezcla previa 5 filas.
  Semilla 295825240 fija; no barrido de parámetros ni umbrales.
- Mismas etiquetas por candidata G-79, incluyendo preguntas sin dato. Nada
  de palabras, nombres, identificadores o claves en los rasgos de entrada.
- Reutilizar `selection` PAR-2 para enseñar fuera de cada mitad, elegir y
  calibrar la candidata elegida; corregir empates con G-68. Pesos finales con
  todo TRAIN. Citar desde 0,4, como antes.
- Enseñar antes de abrir DEV G-62/63/64. Guardar modelos y costos. No usar la
  panadería del usuario, duxiV2 ni reserva nueva para enseñar o elegir.

## Variantes y controles

Base y G-79 deben reproducir sus respuestas exactas. Principal: árboles con
25 rasgos y seis candidatas. Ablaciones: siete rasgos originales G-60 con seis
candidatas; 25 rasgos con una sola candidata (mismos árboles, calibración propia).
Control: etiquetas permutadas entre candidatas del mismo turno, semilla 1.
Reutilizar los ajustes comunes; los árboles no copian frases de enseñanza.

Puertas: ≥310/816 útiles, ≤74/488 citas sin dato; ≥491/816 candidatas elegidas
correctamente (al menos dos puntos sobre 474 de G-79); ≥17 útiles más que cada
ablación y que el control barajado. Es una puerta parcial: no equivale al 60 %
de **respuestas emitidas útiles**, ni a utilidad juzgada por humanos.

Bot.answer con historial, citas literales, desactivación exacta frente a base y
G-79, recarga de base completa en proceso nuevo/hashseed 1 con el mismo código
experimental. p95 y máximo <5 ms. Si pasa, revisión, integración y reserva/juez
independientes antes de promover; si falla, conservar el resultado sin retoques.

## Presupuesto y pruebas

Enseñanza/preparación ≤600 s CPU, evaluación ≤200, total ≤800, RAM conjunta
≤1 GiB, tiempo transcurrido ≤1 000 s. Un proceso pesado. Guardar interrupciones.
Congelar `freeze-G81-prototipo` antes del ensayo. Pruebas focales: aprendizaje
de combinación y cambio con contraejemplos; selección/calibración cruzada
reutilizada; restauración y base recargada. Trece rápidas del proyecto.
