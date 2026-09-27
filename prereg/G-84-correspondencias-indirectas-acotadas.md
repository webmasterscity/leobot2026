# G-84 · Correspondencias indirectas aprendidas con alcance limitado

27 de septiembre de 2026. Preregistro antes de implementación y resultado.

## En palabras fáciles de entender

Leobot aprendió algunas conexiones directas entre palabras de preguntas y
respuestas. Puede faltarle una conexión aunque haya aprendido otras dos que
la relacionen por un paso intermedio. Probaremos esa posibilidad manteniendo
por separado la información directa y la indirecta. El selector aprenderá si
esa conexión ayuda a encontrar una respuesta. No se tomará una asociación como
prueba de un hecho: seguirá citando el texto del negocio y deberá reconocer
cuando falta información. Se comparará con conexiones intermedias equivocadas.

## Fuente y diferencia con intentos anteriores

[Fried y colaboradores, TACL 2015](https://aclanthology.org/Q15-1015.pdf) estudian
conexiones indirectas para ordenar respuestas. Su componente de alineación de
palabras, sin redes, pasa de 27,33 % a 29,01 % y 30,49 % al incorporar dos y tres
pasos en preguntas inglesas de Yahoo. Un cuarto paso empeora. No son preguntas
de nuestros negocios ni pruebas de abstención. Sus matrices de dos y tres pasos
ocupan 1,8 y 9,7 GB; los tiempos publicados usan diez núcleos. No se importarán
sus variantes neuronales, híbridas o sus cifras como capacidad de Leobot.

La hipótesis compatible es aprovechar un paso intermedio **aprendido** con
límite de tamaño, conservando ambas señales. G-65 solo mezcló puntuación de
alineación directa con la puntuación léxica. G-76 compartió grupos latentes.
G-84 reutiliza el aprendizaje directo G-65 y el selector PAR-2, y prueba
conexiones indirectas explícitas sin añadir otra clase de aprendiz.

## Enseñanza y compilación fijas

Base G-19, referencia PAR-2 y tablas G-78 de G-79, SHA verificados. Reutilizar
`g65.examples` y `g65.train(width=1)`: MFAQ TRAIN humano, exclusión de dominios
de calibración existente, máximo 100 pares por dominio, semilla 57, deduplicación,
apoyo en cinco dominios y cinco vueltas de aprendizaje. No usar pares de negocio
para aprender palabras. Conservar el resultado negativo original G-65.

Representar la probabilidad aprendida P(palabra de pregunta | palabra de respuesta)
por columnas de respuesta. Conservar ocho destinos de mayor probabilidad por
columna, desempate por palabra; normalizar después de truncar y registrar masa
retenida. No añadir conexiones de identidad no observadas ni palabras manuales.
Calcular segundo paso como suma de productos `P(b|a)·P(c|b)`, solo cuando la
palabra intermedia b tiene columna aprendida. Conservar ocho destinos, normalizar
y registrar columnas vacías. No tercer paso ni recorrido hasta convergencia.

Control indirecto: permutar las columnas utilizadas en el paso intermedio entre
las palabras de respuesta, semilla 1, conservando el primer paso y sus fuerzas.
Guardar una tabla compacta con vocabularios, antecedentes de frecuencia y listas
de índices/probabilidades redondeadas a seis decimales. El prototipo reconstruye
índices al cambiar de tabla; contar ese costo de preparación. Base completa debe
seguir cabiendo en el límite de carga existente de 100 MiB.

## Uso como información, no como respuesta

Seis candidatas y 25 rasgos PAR-2 intactos. Para cada paso agregar cuatro rasgos:

- puntuación `g65.alignment_scores`, dividida por cantidad de términos conocidos
  de la pregunta (mínimo denominador uno);
- margen de esa puntuación frente a la mejor otra unidad;
- distancia entre las distribuciones medias de las palabras de pregunta y unidad,
  usando distancia Jensen–Shannon normalizada a [0,1]; valor 1 si falta alguna;
- fracción de palabras distintas de pregunta con distribución disponible.

Usar los cortes `SELECTION_MARGINS` PAR-2 para puntaje/margen y `COVER_BINS`
estables para distancia/fracción. La media usa columnas disponibles normalizadas;
unidades preparadas con el mismo texto y encabezado heredado de G-65. No guardar
preguntas, respuestas, claves o resultados de llamadas anteriores en las tablas.

Comparar principal con dos pasos, control directo (repite sus cuatro rasgos bajo
ambos prefijos, misma capacidad y regularización) y segundo paso confundido.
G-79 y base deben reproducir SHA exacto. Enseñar selector solo con los mismos
seis bancos TRAIN, mitades por negocio, L2=1, 25 iteraciones, tolerancia 1e-6,
calibración con empates G-68, cita desde 0,4. Modelos guardados antes de DEV.
No ajustar límites, mezclas o umbral con DEV; no combinar con G-83 en este ensayo.

## Puertas y controles

DEV gastado G-62/63/64: principal ≥326/816 útiles, ≤73/488 citas sin dato,
≥491/816 elecciones correctas (supera 60 % de selección y +2 puntos sobre G-79),
≥17 útiles sobre **cada** control directo/confundido. Selección no equivale a
respuesta útil: el objetivo del usuario sigue siendo ≥60 % de respuestas útiles.

Literalidad, desactivación exacta, reinicio en proceso nuevo/hashseed 1 con base
completa y mismo prototipo; p95 y máximo <5 ms. La panadería del usuario no enseña
ni selecciona; reserva PAR-6 y duxiV2 cerrados. Si pasa, revisión, integración y
reserva independiente antes de promover; si falla, registrar sin relajar puertas.

## Presupuesto

Preparación/enseñanza ≤600 s CPU, evaluación/controles ≤200, total ≤800;
≤1 GiB RAM conjunta, ≤1 000 s transcurridos, un proceso pesado. Conservar tablas
y costos de preparación, aprendizaje, compilación, ajuste y evaluación. No
subir límites ante fallo. Congelar `freeze-G84-prototipo` antes de medir.
Pruebas focales: conexión de dos pasos y contraevidencia; renombrado consistente
de símbolos; desactivación, persistencia y sustitución de documento. Trece rápidas.
