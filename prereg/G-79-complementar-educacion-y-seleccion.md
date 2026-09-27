# G-79 — comprobar si la educación localizada y el selector se complementan

2026-09-27, previo a código. Prototipo externo; repositorio del motor estable
`11a1ef5836382d81a643cad0b217a8669ce0f2d1` intacto.

## En palabras fáciles de entender

G-78 encuentra mejor la oración correcta y cita menos textos cuando falta el dato,
pero no logra dar más respuestas útiles. La otra investigación mejoró la elección
entre varias oraciones con una medida aprendida de su utilidad. Probaremos las
dos cosas juntas. No basta sumar sus mejoras por separado: deberán mejorar
juntas, frente a cada parte y frente a una enseñanza con etiquetas equivocadas.

## Hipótesis, revisión y procedencia

G-78 aprende pesos léxicos de preguntas humanas: 440 primeras candidatas correctas
frente a 420, pero 267 útiles frente a 269. PAR-2 aprende de 25 rasgos sin palabras
qué candidata resulta útil: 468 primeras correctas, 299 útiles y 70 citas sin dato.
La hipótesis es que los nuevos pesos de palabras mejoran la información de entrada
al selector y permiten recuperar más respuestas sin perder prudencia.

Se revisaron las funciones cambiadas de `leobot/context.py` y el educador PAR-2.
No hay reglas por negocio: cuenta coincidencias, clases aprendidas de palabras,
posición y margen; aprende coeficientes de una regresión logística. Sus categorías
y límites son decisiones genéricas de representación, no significados adquiridos.
No cambiar rasgos, K=6, penalización 1, máximo 25 iteraciones ni umbral 0,4.

Fuente congelada de PAR-2: commit `fe2f3116e8d2bf0a6c76eabfce496dbb4780d973`.
SHA del contexto `3c907f07775aa9da574df693fa043a33ae773adc8ff78ec6470d6a86f93feddd`;
del educador `54d4337cdd9d5bfeaa482cb9ba89de248d2d4fbe45c567e29c62bac9c0397eb1`.
Reutilizar sus funciones desde esos objetos git verificados en el prototipo,
sin modificar ni copiar su worktree ni integrar aún en `leobot/`. El código
efectivo de selección será el de PAR-2, aunque el árbol del motor siga estable:
declarar ambas huellas, no presentarlo como capacidad del motor sin modificar.

Tablas G-78 fijas: `.leobot-data/g78_models.json`, SHA
`630399f00c5aa06e987a564b46544f88340726871fffffa1c173639c40ef6fb7`, variante
`localized`, mezcla 0,75 elegida antes en TRAIN. No elegir de nuevo con DEV.

## Corrección de medida y comparación

La revisión encontró que PAR-2 reutiliza la calibración G-60 que puede separar
puntos de igual puntuación en bloques distintos, defecto ya conocido por G-68.
Primero reproducir PAR-2 publicado, sin corregirlo (299 útiles, 70 citas sin dato).
Después usar la calibración con empates agrupados de G-68 **tanto para el selector
solo como para la combinación**. No atribuir a combinar una mejora debida a corregir
la calibración. Reutilizar los mismos ajustes de pesos en esas dos calibraciones.

Variantes:

- base estable, respuestas exactas de referencia;
- G-78 solo, 267 útiles/57 citas sin dato, también sin selector en prototipo;
- PAR-2 original como control de reproducción;
- selector solo con calibración corregida;
- **G-78 más selector reeducado con calibración corregida**, candidata principal;
- combinación con etiquetas permutadas entre candidatas de cada turno (semilla 1).

Mismos seis bancos TRAIN, particiones por negocio y procedimiento PAR-2 para
enseñar selección. No aprende palabras ni respuestas de esos bancos: las tablas
léxicas vienen de MFAQ/SQAC, las del selector solo de rasgos numéricos/categóricos.
Usar DEV G-62/63/64 gastado, `Bot.answer` con historial, selección sin abstención,
latencia sin guardar resultados de preguntas. Si alguna referencia no reproduce
sus conteos, detener la comparación y explicar antes de seguir.

## Puertas y controles

≥5 puntos útiles sobre base; ≥2 sobre **cada** componente, incluido PAR-2 original
y corregido; ≥2 sobre confundido; citas sin dato ≤74/488. Evidencia literal,
desactivación exacta; guardar base completa y recargar en proceso nuevo/hashseed 1
con el mismo componente de código congelado. No es aún `Bot.load` de producción
con selector integrado. p95 y máximo <5 ms. No promover si falla alguna puerta.

Si pasa, revisar e integrar el selector en el motor y repetir en reserva nueva
con autores/juez independientes, renombrado, otro negocio y regresión; alcanzar
esta puerta parcial no equivale a la meta del usuario de ≥60 %.

## Presupuesto

Preparación/ajuste ≤600 s CPU, evaluación/controles ≤200 s, memoria ≤1 GiB
(incluir padre en espera más hijo), ≤1 000 s transcurridos. Un proceso pesado.
Guardar cada tabla antes de continuar. Pruebas focales: desactivación, propiedades
del selector, empates de calibración y reutilización de código. Congelar como
`freeze-G79-prototipo` antes de medir. Conservar costos e interrupciones.
