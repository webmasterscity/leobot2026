# G-70 — correspondencias condicionadas por palabras vecinas

Fecha: 2026-09-27. Registro antes del prototipo. Base estable G-19 y base educada
persistente reconstruida; motor `11a1ef5836382d81a643cad0b217a8669ce0f2d1`.

## Causa e hipótesis

G-69 amplió el puente mediante aprendizaje competitivo: 275/816 citas útiles
frente a 269/816, mismas 74/488 citas cuando falta el dato. No alcanza +5 puntos.
El puente de palabras aisladas mezcla sentidos distintos de una misma palabra.
G-65 ya probó pares contiguos para puntuar, sin usar esas relaciones como evidencia
de qué partes de la pregunta se explican. G-70 prueba ese uso contextual.

Sustrato: palabras y pares contiguos, conteos por dominio, la alineación estadística
ya implementada en G-65 y el consumidor de puente G-57. Ninguna palabra, campo de
negocio o sentido se escribe a mano. Antecedentes, versiones y límites: G-65
(alineación de frases) y G-68 (confianza). No se afirma novedad bibliográfica.

## Diseño fijo

Misma muestra MFAQ y mismas exclusiones G-65. Entrenar la variante de pares de
G-65 sin modificar su algoritmo; de sus asociaciones conservar como destinos
solo palabras individuales que el índice existente puede localizar. Fuentes
de dos palabras, apoyo conjunto en cinco dominios, elevación 4, doce destinos
por fuente; Bayes y exceso sobre frecuencia de fondo como G-69. Sin relajar
estas cantidades después de observar resultados.

Cuando el par aparece en una pregunta, cada una de sus palabras puede recibir
la evidencia de sus destinos aprendidos. Dividir el peso por dos para compartir
la contribución entre las dos palabras. Se combina por máximo con el puente
estable, evitando sumar dos veces un mismo destino para la misma palabra.
El prototipo prepara esa tabla temporal para la consulta y llama al selector
original. Debe restaurarla después de cada llamada: nunca queda una expansión
de una persona para la siguiente. No se promueve una modificación de métodos
en tiempo de ejecución: si funciona, se integra explícitamente en el motor.

Comparación única: base frente a puente condicionado, recontando confianza con
los mismos datos y algoritmo de G-62, umbral 0,4. Control adicional necesario
para promover: mismo conjunto de pares pero sin exigir su coaparición en la
pregunta (mide que importa el contexto y no solo añadir palabras).

Desarrollo separado: G-62/G-63/G-64, material gastado, 816 preguntas directas/sí-no.
Puerta parcial: ≥5 puntos útiles sobre base, sin más citas cuando falta el dato.
El objetivo total permanece ≥60 %, cero invenciones observadas y <5 ms.
El ejemplo visible del usuario se evalúa después, no entra a enseñar ni elegir.

Si pasa: integrar enseñanza e inferencia genéricas, pruebas focales de aislamiento
entre consultas y persistencia, congelar, reserva nueva de 24 negocios y juez
independiente. No se promueve por este desarrollo ni por acertar la panadería.
Controles de reinicio, renombrado, retirada, dato incompatible, puente barajado,
bot fresco y misma información, más regresión y latencia antes del tag. Si no
pasa desarrollo se declaran no corridos, sin tratarlo como refutación de toda G.

## Presupuesto

≤10 min CPU de aprendizaje, ≤5 min de evaluación, ≤1,5 GB adicionales, dos procesos
pesados máximo. Congelar también el script del prototipo antes de correrlo;
registrar huellas antes/después, CPU por fase, asociaciones, RAM y tiempos.
Una comprobación de control debe confirmar que con expansión vacía el selector
da la misma respuesta que la base. No bajar umbrales ni añadir pistas del usuario.

## En palabras fáciles de entender

Una palabra puede tener varios sentidos. Vamos a comprobar si Leobot aprende
mejor la relación con un texto cuando también mira la palabra que tiene al lado.
Lo aprenderá con preguntas reales y tendrá que mejorar al cambiar de negocio.
No enseñaremos ni programaremos la respuesta de la panadería como arreglo.

## Resultado de desarrollo (2026-09-27)

No pasó: 262/816 útiles frente a 269/816, 60/488 citas sin dato frente a 74/488. Control de expansión vacía idéntico. Caso completo sigue sin horario/dirección. CPU 69,5 s; RAM 891 MiB. Motor intacto. Auditoría independiente pendiente.
