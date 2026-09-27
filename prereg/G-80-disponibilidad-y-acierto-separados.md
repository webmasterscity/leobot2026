# G-80 · Aprender por separado si corresponde responder y qué frase sirve

Preregistrado el 2026-09-27, antes de implementar o medir. Desarrollo gastado;
no reserva, no promoción. Base estable y código efectivo PAR-2 como G-79.

## En palabras fáciles de entender

La última combinación da más respuestas útiles, pero también cita más veces
cuando el texto no permite responder. Probaremos dos aprendizajes separados:
uno mira el conjunto de frases y estima si corresponde responder; el otro
elige la frase más útil entre las posibles. Ambos aprenderán de ejemplos ya
etiquetados. No se escribirá qué palabras significan horario, dirección u otra
cosa propia de un negocio. La prueba debe conservar una mejora útil y reducir
las citas que no aportan el dato. Si falla, se conserva el resultado negativo.

## Fuente y diferencia respecto a lo existente

[Wagner, versión 1 del 9 de julio de 2026](https://arxiv.org/html/2607.08456v1)
separa acierto de una respuesta y posibilidad de responder. Sus pruebas usan
modelos neuronales de 2 a 14 mil millones de parámetros; las muestras correctas
de algunas comparaciones son pequeñas y parte de la separación proviene del
vocabulario de los bancos. Usa particiones independientes para elegir y comprobar
límites de error, y declara 15–30 minutos por 1 000 casos en modelos de 7–8 mil
millones. No acredita menos de 5 ms ni un mecanismo compatible por sí solo.
La hipótesis que se toma es la separación de las dos etiquetas; no se trasladan
sus redes, resultados ni certificados. G-80 no tendrá certificación estadística.

PAR-2/G-79 aprende un único acierto por candidata, mezclando preguntas sin dato
con elecciones equivocadas. G-80 reutiliza su regresión logística y rasgos, pero
enseña elegibilidad de la pregunta y acierto condicionado a esa elegibilidad.
No duplica el optimizador ni añade un servicio al motor.

G-79: 326/816 útiles, 90/488 citas sin dato, 474/816 elecciones correctas.
Una puerta que conserve exactamente esa elección tiene techo 58,1 %, por debajo
del 60 %. Aquí se reeduca también la elección; si no mejora ese techo, esta fase
solo puede aportar prudencia. No cambiar esta interpretación tras medir.

## Datos, etiquetas y representación

- Mismos seis bancos TRAIN de G-68, mismas mitades SHA por negocio; DEV G-62/63/64
  solo después de congelar todo. Panadería del usuario y negocios duxiV2 excluidos.
- Tablas G-78 `localized`, mezcla 0,75 fija; SHA y base según G-79. Referencia
  PAR-2 `fe2f3116e8d2bf0a6c76eabfce496dbb4780d973` con SHA verificados por G-79.
- Los mismos turnos y seis candidatas de PAR-2. Etiqueta A=0 para `abstenerse`
  o `derivar`, A=1 para los demás turnos admisibles con claves. Esto mide permiso
  de citar según la anotación, **no** existencia universal de una respuesta ni
  obediencia aprendida a instrucciones de derivación.
- Etiqueta C por candidata: contiene todas las claves, como G-79. Enseñar C solo
  en turnos A=1. Todos los ejemplos A=0 siguen enseñando al aprendiz A.
- C conserva los 25 rasgos y límites PAR-2. A recibe un resumen sin palabras de
  esas mismas seis candidatas: mínimo y máximo para cada campo ordinal escrito
  como entero; para los demás campos, valor más frecuente (empate lexicográfico)
  y cantidad de valores distintos limitada a dos; además cantidad de candidatas.
  Son operaciones genéricas programadas, no significados aprendidos. No usar
  nombres, texto del negocio, identificadores, claves ni acción como entrada.

## Aprendizaje y decisión congelados

Reutilizar `fit`, `score` y `table_of` de PAR-2: L2=1, máximo 25 iteraciones,
tolerancia 1e-6. Aprender A y C en la mitad contraria al negocio puntuado.
Calibrar A con todos sus puntos fuera de enseñanza; calibrar C con la candidata
de mayor puntuación de cada pregunta A=1 fuera de enseñanza. Usar la calibración
con empates agrupados G-68. Reajustar pesos finales con todo TRAIN.

Elegir candidata con C; citar si P(A) × P(C|A) ≥0,4. Sin ajuste adicional del
producto ni búsqueda de umbral. Las calibraciones son estimaciones, no garantías
ni una prueba de independencia. Mantener reglas genéricas de voz y cita literal.

Variantes: base, G-79 reproducido, selector PAR-2 solo reproducido, principal
factorizada, C con A constante igual a la proporción aprendida en TRAIN, y C
con A enseñada con etiquetas permutadas dentro de cada negocio (semilla 1).
Las dos últimas conservan exactamente el C principal. Así se comprueba si el
aprendizaje de disponibilidad aporta algo más que una penalización constante.
Guardar resultados fuera de enseñanza y tablas antes de abrir DEV.

## Puertas y controles

- Principal ≥310/816 útiles (≥5 puntos sobre base y pérdida ≤2 puntos frente
  a G-79), citas sin dato ≤74/488. No rescatar variantes mirando DEV.
- Aporte de A: frente a **cada** control de A, ≥10 citas sin dato menos y pérdida
  de útiles ≤16. Si no, no atribuir mejora a separar el aprendizaje.
- Citas literales, restauración exacta de base y G-79, proceso nuevo/hashseed 1
  con base completa y mismo código experimental; p95 **y máximo** <5 ms.
- Registrar techo sin abstención y denominadores de A/C; las claves automáticas
  no sustituyen al juez humano. Incluso pasar aquí solo habilita revisión,
  integración del código y reserva nueva independiente antes de promover.

## Presupuesto y pruebas

Preparación/enseñanza ≤600 s CPU, evaluación/controles ≤200 s CPU, total ≤800,
≤1 GiB RAM conjunta padre+hijo, ≤1 000 s transcurridos. Un proceso pesado.
Guardar interrupciones y costos. Congelar `freeze-G80-prototipo` antes de medir.
Pruebas focales: aprendizaje de A aun con C equivocado; ausencia de fuga entre
negocios; invariancia del resumen al orden de candidatas; cambios por feedback;
desactivación y sustitución del documento sin conservar pregunta anterior.
