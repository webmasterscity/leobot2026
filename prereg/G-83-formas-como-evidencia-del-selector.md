# G-83 · Usar formas aprendidas como información para elegir y citar

27 de septiembre de 2026. Antes del código y resultados. Desarrollo gastado.

## En palabras fáciles de entender

La prueba anterior encontró 50 fallos donde una forma de cifra o signo aprendida
podría ayudar y la frase correcta ya está entre las seis que se consideran.
Ahora enseñaremos al selector a aprovechar esa pista junto con las que ya usa.
No se le dirá a mano qué forma corresponde a una hora, precio u otro dato.
También aprenderá de ejemplos donde la forma aparece pero no responde la pregunta.
Para aceptar la prueba deberá conservar más respuestas útiles y evitar las citas
cuando falta el dato. El límite favorable sigue por debajo del 60 %: es un paso
parcial, no una solución completa prometida.

## Hipótesis, fuentes y límites

PAR-1 ya aprendió 78 asociaciones palabra→forma de 33 787 pares MFAQ humanos.
Su incorporación directa a la puntuación no mejoró utilidad. G-83 prueba otra
función: **mostrar esa información separada al selector aprendido** para que
aprenda cuándo ayuda, sin cambiar las seis candidatas ni sus puntuaciones léxicas.
La fuente y SHA son los de G-82; se usa su copia independiente verificada.
El analizador de formas es exactamente `chunk_form` de `freeze-PAR-1b`.

G-79 usa 25 rasgos: cuenta si hay cifras pero no la compatibilidad aprendida
entre pregunta y forma del dato. G-80/G-81 mostraron que cambiar solo cómo se
decide con esas pistas no basta. No añadir otra clase de aprendiz.

## Representación y enseñanza fijadas

Mantener referencia PAR-2 congelada, base G-19 y tablas léxicas G-78 de G-79.
Agregar cinco rasgos sin palabras ni formas literales en sus valores:

- cantidad de términos distintos de la pregunta con alguna asociación a forma;
- cuántos de esos términos tienen una forma asociada presente en la unidad;
- cuántos quedan sin esa correspondencia;
- mayor fuerza aprendida entre las asociaciones presentes;
- mayor especificidad de una forma presente: `1-(unidades_con_forma+0,5)/(N+1)`.

Los tres conteos se limitan a dos, como los conteos PAR-2. Fuerza usa cortes
`PI_BINS` estables y especificidad `COVER_BINS` estables. Formas propias de cada
unidad, sin heredarlas del encabezado; N incluye las unidades del documento,
igual que el estimador estable. Estas operaciones son soporte programado;
las asociaciones y su utilidad se aprenden. No asignarles significados manuales.

Mismo `fit`/`selection` PAR-2, K=6, L2=1, 25 iteraciones, tolerancia 1e-6,
calibración G-68 por mitades de negocios, cita desde 0,4. Mismos seis bancos
TRAIN y DEV G-62/63/64. Enseñar/guardar antes de DEV. No seleccionar pesos,
umbrales o variantes con DEV. Panadería del usuario y reserva PAR-6 excluidas.

## Comparación y puertas

Base y G-79 reproducen respuestas exactas. Enseñar y medir: principal con cinco
rasgos nuevos, control sin ellos (debe reproducir G-79) y control con listas
de asociaciones reasignadas entre palabras de pregunta, semilla 1, manteniendo
destinos/fuerzas y cantidad total de enlaces. No regenerar asociaciones.

Principal: ≥326/816 útiles (≥2 puntos sobre G-80 y conserva G-79), ≤73/488
citas sin dato, ≥17 útiles más que el control barajado. Registrar elección
sin abstención, pero no convertirla en utilidad ni exigir un cambio de orden
si la ganancia está en reconocer cuándo citar. Citas literales, desactivación
exacta, base completa recargada en proceso nuevo/hashseed 1 con mismo prototipo,
p95 y máximo <5 ms. Si falla, conservar el resultado sin ajustar la puerta.
Si pasa, revisión/integración/reserva independiente antes de cualquier promoción.

## Presupuesto y pruebas

Preparación/enseñanza ≤600 s CPU, evaluación/controles ≤200, total ≤800,
tiempo transcurrido ≤1 000 s, RAM conjunta ≤1 GiB. Un proceso pesado.
Congelar `freeze-G83-prototipo` antes de medir. Pruebas focales de cambio por
enseñanza, documento nuevo, renombrado de cifras y persistencia/desactivación.
No conservar respuestas a preguntas anteriores como atajo de latencia.
