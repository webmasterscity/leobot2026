# G-95 — competencia entre correspondencias aprendidas

2026-09-27. Antes de implementar y medir.

## En palabras fáciles de entender

Una sola palabra del texto puede parecer relacionada con varias palabras de
la pregunta. Contar cada relación por separado puede dar más confianza de la
que merece. Probaremos otra vista: repartir las conexiones aprendidas sin usar
dos veces la misma palabra del texto. Esto también puede perjudicar respuestas
correctas, porque una palabra puede expresar una frase entera. Por eso será
solo una señal que el selector aprende a valorar, nunca una regla que prohíba
responder. La comparación decidirá si aporta algo más que contar las mejores
conexiones independientes.

## Hipótesis, fuentes y diferencia

G-65/G-84 suman coincidencias probabilísticas de cada término por separado.
G-48 comparó caminos de árboles, G-75 relaciones léxicas y G-86 fragmentos con
orden. Ninguno enfrenta las conexiones de distintas palabras por una misma
palabra candidata. G-93 y G-94 no mejoraron la elección; no se incorporan.

[Yih y colaboradores, 2013](https://aclanthology.org/P13-1171.pdf) estudian
conexiones entre palabras para elegir respuestas. Su formulación admite varias
palabras de pregunta por palabra de respuesta; **no demuestra que imponer
una a una sea mejor**. Además, combina conocimiento léxico, componentes
neuronales y reglas manuales de tipos de respuesta. No usar esos componentes.
[OTAlign, 2023](https://aclanthology.org/2023.acl-long.219.pdf) muestra la
importancia de permitir palabras sin conexión y relaciones de varias palabras;
sus vectores son neuronales. La
[prueba de detección de invenciones de agosto de 2026](https://arxiv.org/html/2608.15804v1)
muestra límites de usar alineación como prueba de veracidad, incluso con vectores
neuronales. Esos trabajos motivan los controles y la posibilidad de fallar,
no permiten atribuir comprensión a nuestra asignación.

Hipótesis propia y acotada: la competencia entre conexiones contiene información
adicional para elegir una cita. Alternativa: la evidencia léxica es insuficiente
o las conexiones múltiples son necesarias, y restringirlas no ayuda. Solo se
añade un cálculo de asignación al prototipo externo, no otro aprendiz ni ruta de
respuesta. Si funciona, se compararía después con sustituir señales redundantes
de alineación. No declarar relaciones semánticas, papeles o inferencias por ello.

## Datos y cálculo fijos

Base y G-84 directo con sus huellas, mismo PAR-2 verificado. No otra enseñanza
de palabras ni más ejemplos. Reusar columnas aprendidas `one` de G-84, sus
antecedentes de frecuencia y los mismos índices de palabras de unidades,
incluidos encabezados heredados como en G-65. No añadir enlaces por identidad
que no hayan sido aprendidos. Sin diccionarios, etiquetas G-91 ni clases G-93.

Para una pregunta y una de las seis candidatas actuales:

- Nodos: términos distintos de pregunta presentes en el vocabulario aprendido
  y términos distintos de la unidad presentes en sus columnas. Usar todos ellos,
  sin truncar por palabras vistas en la evaluación.
- Peso positivo de conexión: `max(0, log(P(q|a)/P(q)))`, de las tablas existentes.
  Una conexión ausente vale cero. No conectar obligatoriamente una palabra.
- Vista libre: suma de máximos por palabra de pregunta; permite reutilizar una
  palabra de respuesta. Vista competitiva: suma máxima con a lo sumo una conexión
  por cada nodo. Implementar asignación rectangular con columnas vacías de peso
  cero, descartando filas/columnas totalmente nulas antes de calcular; no elegir
  conexiones por codicia. Ambas sumas se redondean a seis decimales antes de
  formar variables, para estabilidad numérica.
- Registrar tamaño máximo de matrices y costo. La asignación no condiciona
  directamente abstenerse o responder: solo produce información para aprender.

Mantener las 33 variables y seis propuestas del selector. Agregar cuatro:
peso total dividido por términos conocidos de pregunta (mínimo divisor uno),
margen frente a mejor otra de estas seis candidatas, fracción de peso libre que
se pierde por competencia (cero sin peso), proporción de términos distintos de
pregunta conocidos. Usar `SELECTION_MARGINS` existentes para peso/margen,
`COVER_BINS` para fracciones. En vista libre la pérdida es cero. No retocar bins.

Cuatro variantes: sin señales nuevas; vista libre; vista competitiva principal;
competitiva con columnas de respuesta permutadas, semilla 1, solo en la señal
nueva. Las 33 variables antiguas conservan sus correspondencias reales en todas.
Misma cantidad de variables en los tres tratamientos; una variable puede ser
constante en el control libre. Guardar solo modo/semilla y tablas aprendidas.

## Enseñanza, comprobación y puertas

Mismos seis bancos TRAIN y 3 520 turnos/20 629 candidatas, mitades por negocio;
selector existente L2=1, 25 iteraciones/tolerancia 1e-6, calibración isotónica
con empates G-68 y cita desde 0,4. Los cuatro modelos se guardan antes de DEV.
DEV G-62/63/64 gastado; panadería, PAR-6 y duxiV2 no se usan para enseñar o elegir.

Principal ≥368/816 útiles, ≤73/488 citas sin dato, ≥491/816 elecciones correctas,
≥17 útiles sobre vista libre y confundida. Cero citas no literales, base completa
<100 MiB, desactivación exacta, recarga/hashseed 1 exacta, p95 y máximo <5 ms.
Sin señal debe reproducir SHA G-84 directo y base. Registrar todos los resultados,
sin cambiar criterio ni escoger un control al ver DEV. Meta final ≥60 % útil
todavía requiere prueba independiente; este ensayo no la sustituye.

Presupuesto: preparación/enseñanza ≤600 s CPU, evaluación/guardado/recarga ≤200,
total ≤800 s, pared ≤1 000 s, RAM conjunta ≤1 GiB, un proceso pesado. Costo
anterior G-84 aparte. Focales: caso donde elección codiciosa falla, ausencia de
conexiones, una palabra reutilizada, comparación con enumeración exhaustiva
pequeña, permutación de nodos y sustitución de documento/desactivación. Trece
rápidas; registrar cualquier límite no cumplido. Congelar `freeze-G95-prototipo`
antes de medir. Motor/base del usuario intactos.
