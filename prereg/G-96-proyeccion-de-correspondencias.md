# G-96 — proyección de correspondencias aprendidas

2026-09-27. Plan y criterios anteriores a implementación y medición.

## En palabras fáciles de entender

Dos expresiones diferentes pueden pedir el mismo dato. Leobot ya aprendió
conexiones entre palabras, pero suele examinarlas por separado. Esta prueba
busca patrones compartidos en el conjunto de esas conexiones. Representará
cada palabra con una lista corta de números aprendidos, sin redes neuronales.
La pregunta y cada posible cita se compararán mediante esas listas. Después,
el selector existente aprenderá si esa comparación ayuda a contestar.

Esto puede perder diferencias esenciales y empeorar las respuestas. Se
comparará con las conexiones completas, con una reducción al azar y con
palabras deliberadamente confundidas. Una cita del mismo tema que no conteste
seguirá contando como fallo. No se enseñará la solución de la panadería ni
respuestas del investigador. La meta del 60 % sigue pendiente de examen nuevo.

## Decisión, fuentes y admisión

El usuario propone estudiar cómo resuelve preguntas el investigador. No hay
acceso al código, parámetros ni cálculos internos del modelo de lenguaje;
una explicación producida por él no constituye esa inspección. La propuesta
se traduce en una hipótesis comprobable sobre relaciones aprendidas entre
expresiones. No se usan respuestas de un LLM como material educativo (5.7).

[LSA, 1990](https://www.microsoft.com/en-us/research/publication/indexing-by-latent-semantic-analysis/)
motiva representar relaciones de palabras por unas pocas direcciones comunes.
[Halko, Martinsson y Tropp, versión de diciembre de 2010](https://arxiv.org/pdf/0909.4061)
aporta el algoritmo 4.4: multiplicaciones alternadas y normalización entre
ellas, para evitar perder precisión numérica. Usaremos su aproximación
`A ≈ Q(QᵀA)`, sin calcular una descomposición singular completa ni invocar
sus garantías como prueba de comprensión.

[LASER-QA, 2017](https://aclanthology.org/D17-1089.pdf) une información de
preguntas y respuestas, pero recupera episodios anteriores y calcula vecinos
al recibir cada pregunta. No se adopta ese mecanismo: aquí solo se puntúan
fragmentos del documento actual mediante tablas numéricas compiladas.
[Jain y Garimella, EACL 2026](https://aclanthology.org/2026.findings-eacl.217/)
estudian si el contexto permite responder; su método genera hipótesis con
modelos de lenguaje. El resumen consultado no aporta un método compatible que
podamos importar. Refuerza distinguir semejanza de información suficiente,
medida aquí con las preguntas sin dato existentes.

Fallo concreto: las correspondencias aisladas G-65/G-84 no ofrecen evidencia
suficiente para elegir y autorizar muchas citas. Hipótesis: una aproximación
conjunta suaviza conexiones escasas y mejora esa elección. Alternativa: borra
diferencias y solo aproxima temas. G-76 aprendió una mezcla de 32 grupos con
probabilidades por par completo; G-84 hizo dos pasos locales por conexiones;
G-95 impuso competencia entre conexiones. Ninguno hizo esta proyección lineal
con componentes de ambos signos. No es una mejora de orden o participantes:
esa investigación queda pendiente y no se atribuirá a G-96. Si funciona, se
comparará sustituir representaciones redundantes de alineación, no acumular
rutas indefinidamente. Prototipo externo, sin cambios de motor.

## Cálculo fijado

Reutilizar la base y las tablas G-84 directas verificadas. Sin nuevos corpus
ni aumentar vocabulario. Matriz dispersa `A[q,a] = max(0, log(P(q|a)/P(q)))`;
conexión ausente = 0. Usar las columnas `one` normalizadas por el decodificador
G-84, como G-95. Sin conexiones por identidad añadidas a mano.

- Principal: 32 direcciones como máximo, semilla 1, dos iteraciones del
  algoritmo 4.4. Inicio gaussiano en el lado de respuestas. Normalización
  mediante Gram-Schmidt modificado con dos pasadas, eliminación de direcciones
  residuales de norma ≤1e-10. Sin aumentar rango ni iteraciones después.
- Guardar filas de `Q` y columnas de `B=QᵀA`, con doce decimales. La señal es
  el producto de los promedios de filas de las palabras conocidas de pregunta
  y respuesta: promedio de `QQᵀA` entre sus términos distintos. No aplicar
  máximo con cero al resultado de la proyección. Sin recortes de longitud.
- Control completo: promedio de las entradas de `A` entre esos mismos
  términos, sin compresión. Control al azar: base ortonormal de 32 direcciones
  gaussianas en el lado de preguntas, semilla 1, y `B=QᵀA`, sin aprender `Q`.
- Control confundido: permutar las columnas aprendidas de respuesta con
  semilla 1, conservando `Q` y las 33 señales antiguas. La matriz `AAᵀ` es
  invariante a esa permutación; no es necesario volver a descomponerla.
- Conservar las seis propuestas y las 33 variables G-84. Añadir cuatro:
  señal media, margen contra la mejor de las otras seis, proporción conocida
  de pregunta y proporción conocida de texto candidato. Para esta última,
  incluir el encabezado solo como ya lo hace G-65. Redondear señal y margen
  a seis decimales; intervalos `SELECTION_MARGINS` y `COVER_BINS` existentes.
  Preparar promedios de las unidades en `load_context`; ninguna memoria de
  preguntas, respuestas ni episodios educativos durante inferencia.

Cinco variantes: sin señal nueva, matriz completa, proyección al azar,
proyección aprendida principal, proyección confundida. Registrar error de
aproximación y costo de construir las tablas; menor error matricial no es
mejor comprensión. Los cuatro tratamientos tienen las mismas variables.

## Datos, controles y puertas

Mismos seis bancos TRAIN, 3 520 turnos/20 629 candidatas, mitades por negocio;
selector existente L2=1, 25 iteraciones, tolerancia 1e-6, calibración isotónica
con empates G-68 y umbral 0,4. Guardar los cinco modelos antes de DEV. DEV
G-62/63/64 está gastado. Panadería, PAR-6 y duxiV2 no se leen para educar o
elegir. No hay nueva reserva ni promoción en esta prueba.

Principal ≥368/816 útiles, ≤73/488 citas sin dato, ≥491/816 elecciones correctas,
≥17 útiles por encima de cada control completo, al azar y confundido. Cero
citas no literales; no equivale a garantía universal de veracidad. Base <100
MiB, retirada exacta, recarga en otro proceso/hashseed 1 exacta. p95 y máximo
<5 ms. Sin señal reproduce SHA G-84 directo y la base original. El fracaso
de principal no se rescata eligiendo otro tratamiento después de ver DEV.

Presupuesto: preparación/enseñanza ≤600 s CPU, evaluación/guardado/recarga
≤200, total ≤800, pared ≤1 000, RAM conjunta ≤1 GiB; un proceso pesado.
G-84 previo se declara aparte. Pruebas focales y trece rápidas con timeout
40 s. Congelar `freeze-G96-prototipo` antes de medir calidad.

## Ejecución y comprobaciones

1. Crear `experiments/test_g96_projected_alignment.py`: matriz de rango uno
   reconstruida, direcciones ortogonales, matriz vacía/nula y dependencias;
   proyección de rango limitado ante dirección dominante conocida; producto
   de promedios igual al promedio de entradas; cambio de documento y retirada.
   Verificar fallo por ausencia del módulo antes de implementar.
2. Crear `experiments/g96_projected_alignment.py`: operaciones dispersas,
   proyección y enlace reversible sobre `DirectBinding`; enseñanza y medición
   con los componentes G-95 existentes, sin copiar otro selector. Registrar
   fuente, huellas, presupuesto y todas las variantes. Ejecutar focales y
   rápidas; congelar código. Revisar correspondencia con este preregistro.
3. Ejecutar `timeout 1000s env PYTHONHASHSEED=0 python3 -m
   experiments.g96_projected_alignment`, guardar cifras en
   `results_v3/g96_projected_alignment.json`, tablas fuera del motor bajo
   `.leobot-data/g96/`; conservar interrupciones. Actualizar `LEOBOT_STATE.md`
   con decisión y límites, sin integrar si falla alguna puerta.
