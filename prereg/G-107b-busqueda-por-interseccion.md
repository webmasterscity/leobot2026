# G-107b — Búsqueda por intersección en el saber general

Fecha: 2026-09-29. Estado: diseñado (precede al código). Motor: `537cb71` (con el almacén de G-106/G-107). Sustituye el paso 3 de G-107
(elegir una relación por plantillas), que dio 0/102 en desarrollo (`results_v3/g106_g107_desarrollo.md`).

## Qué fallo concreto resuelve
Las preguntas cotidianas del banco de desarrollo D1 piden el término a partir de sus relaciones, al revés de como está guardado
(«¿Qué cubierto se usa para tomar la sopa?» → cuchara; «¿Qué animal tiene trompa?» → elefante). Techo medido en D1: la respuesta está
en el almacén en 86/102; enlazada directamente (una relación, cualquier sentido) con alguna palabra de contenido de la pregunta en 40;
con todas, en 6.

## Por qué los mecanismos actuales no bastan
La ruta por plantillas necesita saber qué relación se pide y contestar el otro extremo; la lectura solo contesta desde frases.
Ninguna combina varias restricciones a la vez.

## Mecanismo (principio general de memoria semántica: búsqueda por intersección)
1. Palabras de la pregunta: las de contenido según las clases aprendidas de AnCora (sustantivo, nombre propio, adjetivo, verbo)
   que están en el almacén.
2. Candidatos: todo término enlazado por una relación (cualquiera, en cualquier sentido) con alguna de esas palabras y que no es una
   de ellas.
3. Puntuación: suma, sobre las palabras de la pregunta enlazadas con el candidato, de 1 / log(2 + grado de la palabra) (una palabra
   con muchos enlaces informa poco). Sin listas de palabras ni de relaciones.
4. Se contesta el mejor candidato solo si está enlazado con al menos 2 palabras distintas de la pregunta y su puntuación es
   estrictamente mayor que la del segundo; si no, «No lo sé». Solo preguntas abiertas (con palabra interrogativa aprendida);
   el sí/no queda como en G-107.
5. La respuesta dice que es saber general y muestra los enlaces que la sostienen. `Bot.answer` del kiosco no usa esta ruta.

## Desarrollo y decisión de ir a reserva
D1 sirve para depurar; **D2 no se mira hasta tener el mecanismo fijo**, y es la comprobación de desarrollo. Se pide reserva (banco nuevo
de ≥ 300 preguntas de ≥ 6 redactores independientes de ≥ 2 familias, juez ciego doble) solo si en D2, con conteo automático:
correctas ≥ 10 % de las contestables y correctas ≥ 60 % de las respuestas dadas. Si no, se registra negativo y no se gasta reserva.

## Umbrales en la reserva (fijados ahora)
Los de G-107: correctas ≥ 15 % de las contestables; entre las respuestas dadas, correctas o parcialmente correctas ≥ 80 %; saber
barajado ≤ un tercio del tratamiento; `respond` p95 ≤ 10 ms; reinicio y hashseed idénticos.

## Controles
Sin saber general (0 esperado); saber barajado (destinos permutados dentro de cada relación); sin la condición de ≥ 2 enlaces.

## Presupuesto
Sin enseñanza nueva (solo el almacén ya construido); respuesta ≤ 10 ms p95.
