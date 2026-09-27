# G-66 — aprender de respuestas rivales

Fecha: 2026-09-27. Preregistro anterior al código. Base `estable-G-19`, motor
`11a1ef5836382d81a643cad0b217a8669ce0f2d1`. G-65 no pasó desarrollo: 361/633
con palabras, 351/633 con pares, frente a 346/633; objetivo 60 % y +5 puntos.

## Hipótesis y cambio

Contar o alinear correspondencias no penaliza directamente preferir una respuesta
ajena de tema similar. Se aprende una función lineal de preferencia mediante
correcciones entre la respuesta propia y otra del mismo sitio. Sus variables son
pares (palabra o secuencia de la pregunta, palabra de la respuesta). Es una tabla
dispersa de coeficientes, sin redes neuronales, representaciones neuronales ni
diccionarios manuales. Toda asociación nace de ejemplos humanos.

Sustrato: conjuntos de palabras y pares contiguos, sumas, norma y minimización
del error de ordenación con margen. Actualización acotada por el error y la norma
del ejemplo (aprendizaje lineal por correcciones, máximo paso 1), cinco vueltas.
No se introducen operadores de horarios, precios, negocios o preguntas concretas.
Antecedente: [Joachims, KDD 2002](https://www.cs.cornell.edu/people/tj/publications/joachims_02c.pdf),
aprendizaje del orden mediante preferencias. Su fuente de señales son clics y
su optimización usa SVM; aquí son pares documentados de MFAQ y actualizaciones
acotadas. Su resultado no demuestra este candidato. La revisión 2026 y las
exclusiones de mecanismos con LLM constan en G-65; no se invoca novedad.

Resuelve la competencia entre respuestas que el puente actual no optimiza.
G-59 restaba frecuencias aisladas: no corregía la preferencia de la función
completa después de cada ejemplo. El control sin actualización distingue ambas.
Si funciona, reemplaza el puente solo si la ablación demuestra que sobra;
no se acumulan rutas sin aporte medido.

## Datos y decisiones previas

Misma muestra humana, exclusiones y deduplicación que G-65 (31 762 pares), sin
respuestas del kiosco para aprender coeficientes. Para cada pregunta, respuesta
rival elegida dentro del mismo dominio mediante semilla. Secuencias con apoyo
en cinco dominios; asociaciones admitidas por aparición positiva, máximo dos
millones (selección por soporte si excede). No se guardan frases completas.

Dos variantes: palabras y palabras más pares en la pregunta (respuesta: palabras).
Cada respuesta se normaliza por raíz de su número de términos; las correcciones
usan la diferencia entre respuestas. Cinco vueltas, negativo rotado por vuelta.
Semillas de orden 0, 1 y 2. Coeficientes finales promediados entre vueltas.
Mezcla con puntaje actual elegida en A–D entre 0, 0,25, 0,5, 1, 2, 4 y 8;
se selecciona por el promedio entre semillas, desempate a menor peso.

Comprobación de desarrollo separada: E–F y bancos gastados G-59/G-60 (633 casos).
Este material fue medido en G-65: queda declarado como desarrollo reutilizado,
nunca se le llamará reserva nueva. Puerta para continuar: promedio ≥60 % y
ventaja ≥5 puntos frente a la base; ninguna semilla por debajo de la base.
Pares se conservan solo si añaden ≥2 puntos sobre palabras.

No se toca la confianza si el techo de selección no alcanza. Si lo alcanza,
enseñanza y respuesta se integran en el motor, se recalibra con los bancos
gastados y se repite el protocolo de reserva y puertas finales de G-65, incluida
la meta del usuario de ≥60 % útil, cero invenciones y p95 <5 ms. Se informa el
costo de aprender; no equivale al de responder.

Controles: sin actualización, rivales barajados, bot fresco, memoria literal,
datos iguales, documento incompatible, retirada, renombrado y reinicio. Las
pruebas estructurales con símbolos no cuentan como lenguaje libre. Auditoría
independiente antes de cerrar el diseño. Si falla, candidato fuera del motor.

## Presupuesto

≤20 min CPU de aprendizaje, ≤10 min de desarrollo, ≤1,5 GB adicionales;
seis modelos en secuencia, máximo dos procesos pesados. Tres semillas obligatorias
porque la enseñanza depende del orden. Reserva y controles: límites de G-65.
Se preservan huella antes/después, CPU por fase, asociaciones, ejemplos y RAM.

## En palabras fáciles de entender

En esta prueba, Leobot ve una pregunta junto a su texto correcto y otro texto
que no la responde. Si prefiere el equivocado, ajusta lo aprendido. Queremos
comprobar si esas correcciones le ayudan con otros negocios. Nadie le escribirá
qué significa cada palabra. Solo se aceptará el cambio si encuentra suficientes
respuestas nuevas, conserva su prudencia y responde a tiempo.

## Resultado de desarrollo (2026-09-27)

Ambas variantes eligen peso cero en A–D; 346/633 en cada una de las tres semillas. Ninguna puerta pasó. CPU 152,7 s; RAM 609 MiB. Auditoría pendiente. Motor sin cambios.
