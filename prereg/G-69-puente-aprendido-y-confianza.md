# G-69 — usar las correspondencias aprendidas también como evidencia

Fecha: 2026-09-27. Antes del prototipo. Motor estable G-19,
`11a1ef5836382d81a643cad0b217a8669ce0f2d1`.

## Hipótesis y diferencia frente a lo descartado

G-68 falló: combinar las mismas siete pistas mediante árboles disminuyó las
citas útiles de 269/816 a 242–245/816. En el caso completo del usuario, el texto
correcto se encuentra pero las palabras sin relación aprendida deprimen su
confianza. El puente estable solo conserva 155 palabras de pregunta y 960
asociaciones, frente a 2443 palabras con evidencia en cinco dominios de G-65.

G-65 solo sumó el puntaje de alineación al selector; nunca usó lo aprendido
para calcular qué partes de la pregunta quedaban explicadas ni reeducó la
confianza resultante. G-69 contrasta ese uso. No afirma que una correspondencia
estadística sea una prueba de significado: las asociaciones falsas deben penalizar
la confianza cuando se reenseña con preguntas sin dato.

Se reemplaza únicamente la tabla aprendida `context_model.bridge`, utilizando
el consumidor existente de G-57. Motor congelado todo el ensayo; sin cambios
de Python operacional, reglas léxicas, plantillas, respuestas externas ni redes.
La fuente y antecedentes de alineación están en G-65. No se presenta este cambio
de enseñanza como un mecanismo nuevo de comprensión o novedad científica.

## Dos candidatos y controles

Muestra humana MFAQ de G-65, misma deduplicación, 31 762 pares y exclusión de
dominios de calibración. Dos tablas, ambas máximo 12 asociaciones por palabra,
excluyendo la identidad y con apoyo conjunto en cinco dominios distintos:

1. **Conteo:** el estimador de exceso sobre frecuencia de fondo de G-57,
   con la nueva evidencia mínima, para medir el efecto de amplitud por separado.
2. **Competencia:** probabilidades de alineación G-65, convertidas con Bayes
   a probabilidades de palabras de respuesta dadas palabras de pregunta;
   exceso sobre frecuencia de fondo, elevación mínima 4, misma forma de tabla.

No se ajusta apoyo ni elevación después de medir. Cinco dominios viene de la
representación preregistrada G-65, no del ejemplo de la panadería.
La tabla G-57 original es el control. No se conserva una rama por pregunta.
Los pesos `delta`, formato de unidades y umbral de cita 0,4 permanecen iguales.

Para cada tabla, recontar la confianza Bayes/isotónica existente con los mismos
bancos de G-62 (G-57 a G-61 y desarrollo A–F); nunca la panadería del usuario.
La selección entre los dos candidatos usa error de probabilidad fuera de
enseñanza, con las dos mitades por negocio del procedimiento histórico.
El ajuste isotónico conserva la implementación histórica para que el cambio
de G-68 sobre empates no se mezcle en el efecto de G-69.

Desarrollo de comprobación: G-62/G-63/G-64, 816 preguntas directas y sí/no,
material gastado que no cuenta como reserva. Medir selección, respuestas útiles,
falsas citas ante dato ausente y costo; no confundir las primeras dos medidas.
El caso del usuario se evalúa solo después de seleccionar, como diagnóstico.

## Puertas y verificación

Puerta de mejora parcial: ≥5 puntos útiles sobre el mismo control en 816 casos
sin aumentar citas en preguntas sin dato (base 269/816 y 74/488). Si no pasa,
se descarta sin cambiar la base que usa el usuario. La meta global sigue siendo
≥60 % útiles, cero inventadas y <5 ms; se declara por separado su cumplimiento.

Si pasa: conservar motor congelado, fijar huella del modelo aprendido y pedir
24 negocios nuevos a un redactor independiente. Guardarlos en Git antes de
contestar; juez ciego antes de una promoción. Cero invenciones observadas, sin
incremento de engañosas respecto a la base y ≥5 puntos útiles. Meta global 60 %
informada aparte, sin inventar que una mejora parcial la cumple.

Controles para promover: asociaciones barajadas, puente apagado con igual
información, bot fresco, documento incompatible, renombrado, cambio de datos,
retirada y reinicio; regresión y latencia fija. El ciclo puede mejorar solo la
educación con idéntico motor, de acuerdo con la misión. Auditoría independiente
antes de cerrar el diseño, pase o falle.

## Presupuesto

Aprender y recalibrar ≤10 min CPU, desarrollo ≤5 min, memoria ≤1,5 GB adicionales;
dos procesos pesados máximo, timeouts explícitos. Informe de ejemplos, asociaciones,
CPU por fase, memoria, p50/p95 de `answer`, huellas de motor y base antes/después.
Sin modificar ni reinterpretar los criterios después de observar resultados.

## En palabras fáciles de entender

Leobot puede acertar qué renglón mirar y aun así no reconocer cómo se relaciona
con la pregunta. Probaremos enseñarle más de esas relaciones con preguntas
reales, y después enseñarle cuándo esas pistas merecen confianza. Tendrá que
ayudar en otros negocios y seguir callando cuando falte información. La prueba
de la panadería no le enseñará ninguna respuesta.

## Resultado de desarrollo (2026-09-27)

No pasó: competencia seleccionada, 275/816 útiles frente a 269/816, ambas 74/488 citas sin dato. Conteo 243/816. El caso completo sigue sin horario/dirección. CPU 49,5 s; RAM 863 MiB. No se sustituyó la base del usuario. Auditoría independiente pendiente.
