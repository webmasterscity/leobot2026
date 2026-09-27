# G-76 — grupos aprendidos de preguntas completas y respuestas

2026-09-27. Previo a implementación. Prototipo externo, motor estable
`11a1ef5836382d81a643cad0b217a8669ce0f2d1`; no modifica la base del usuario.

## En palabras fáciles de entender

Dos preguntas pueden pedir lo mismo aunque sus palabras sean distintas.
Probaremos si Leobot aprende grupos de preguntas y de respuestas a partir de
ejemplos reales. Los grupos no tienen nombres escritos por nosotros: aparecen
al contar qué palabras suelen ir juntas. Ante una pregunta nueva, el grupo
aprendido ayuda a buscar la línea del negocio. Se guardan solo cuentas y
probabilidades, nunca respuestas para repetirlas. Si confunde datos que hablan
del mismo tema, quedará como un intento fallido.

## Causa, antecedentes y diferencia

G-75 no mejoró la elección y aumentó citas sin dato. Predicate Matrix restringía
su alcance a uniones de palabras; G-65/G-70 también condicionaban asociaciones
a una palabra o pareja. Aquí una variable compartida depende de todas las
palabras conocidas de la pregunta y se aprende conjuntamente con las respuestas.
No establece equivalencias semánticas ni extrae respuestas de otros negocios.

[QATM, 2011](https://people.cs.umass.edu/~wallach/workshops/nips2011css/papers/Zolaktaf.pdf)
motiva separar vocabularios de preguntas y respuestas y relacionarlos mediante
grupos. [PLTM, 2009](https://aclanthology.org/D09-1092.pdf) comparte grupos entre
documentos vinculados. Esta prueba reduce la representación a una mezcla de
multinomiales con un grupo por pareja, para comprobar primero si existe señal
barata aprovechable. No reproduce esos artículos ni promete sus resultados.
La revisión de 2026 y límites están en las investigaciones G-71 y contextual.

PAR-1 agrupa palabras individuales; PAR-3 recupera ejemplos completos. Esta vía
no conserva ejemplos y condiciona un grupo a la pregunta entera. Si funciona,
podría sustituir asociaciones marginales del puente; no se añade al motor en
este ensayo. Se reutiliza el contador/calibrador y el evaluador G-68/G-75.

## Educación fijada

- Misma muestra MFAQ de G-65, misma huella y dominios excluidos. Lemas existentes.
- Pregunta de hasta 24 términos, respuesta de hasta 64; conservar como máximo
  4 000 pares, por SHA de dominio y textos normalizados. Cada término aparece
  una vez por lado. Vocabularios separados, apoyo en al menos cinco dominios.
- 32 grupos, 12 rondas de expectativa y recuento (EM). Por pareja, probabilidad
  proporcional al prior del grupo por el producto de probabilidades de términos
  de pregunta y respuesta en sus respectivos vocabularios. Suavizado 0,1 por
  término y uno por grupo. Recontar ambos lados con esas responsabilidades.
- Inicialización por asignación aleatoria de parejas a grupos, semillas derivadas
  de la huella del motor más 0, 1 y 2. Tres modelos; conservar todos y promediar
  sus señales al responder, sin elegir una semilla con los bancos.
- Control: permutar respuestas entre las parejas seleccionadas del mismo dominio
  (semilla 76); conserva vocabulario y tema del sitio. Registrar cuántas cambian.
  Mismas tres inicializaciones, rondas y presupuesto. No duplicar corpus.

## Uso y comparación

Al cargar, estimar probabilidades de grupo para cada unidad a partir del lado
respuesta. Para la pregunta, usar solo el lado pregunta. Señal de la pareja:
logaritmo de la suma sobre grupos de `P(grupo|pregunta) P(grupo|unidad)/P(grupo)`.
Sin términos conocidos, ninguna señal. Promedio de las tres semillas. Índices
y probabilidades compilados; sin análisis sintáctico nuevo ni búsquedas de casos.

Puntuación = original + peso por señal, pesos 0,25; 0,5; 1; 2, más desactivado.
Reconstruir rasgos de la unidad elegida, añadir señal de grupo, ventaja sobre
otras unidades y fracción conocida de pregunta. Cuartiles contados en TRAIN.
Recontar la confianza G-60/G-68, cruce por negocio; umbral 0,4 intacto. Peso
elegido por más útiles entre los que no aumenten citas sin dato; mismos desempates
de G-75. Misma selección independiente para control confundido.

TRAIN: bancos de G-68. DEV: G-62/G-63/G-64, gastados; `Bot.answer` real con
historial, sin almacenar respuestas ni resultados de preguntas previas. Registrar
también primera candidata correcta forzando elección. Son claves automáticas,
no juez humano ni prueba de ausencia de engaño.

Puertas parciales: ≥5 puntos útiles sobre base y ≥2 sobre control confundido;
citas sin dato no mayores que base; evidencia literal, reinicio y desactivación
exactos; p95 y máximo <5 ms. Como prueba de discriminación, informar las tres
semillas sin selección, y que una permutación consistente de símbolos no cambie
las probabilidades. La contraevidencia requiere recontar la fuente: no se declara
aprendizaje incremental ni retiro de hechos en este prototipo de relevancia.
Si pasa, revisión independiente, integración y reserva nueva antes de promover.

## Presupuesto y ejecución

Un proceso pesado; preparación/enseñanza ≤600 s CPU, selección/evaluación ≤150 s,
≤1 GiB RAM, ≤1 000 s transcurridos. Guardar al terminar cada modelo y registrar
costos también si se interrumpe. Pruebas focales con símbolos opacos: dependencia
de toda la pregunta, alineación, cambio de documento, renombrado y persistencia.
Commit de este documento antes de implementar; `freeze-G76-prototipo` antes de
medir. No rescatar un fallo ampliando el presupuesto ni afinando sobre DEV.
