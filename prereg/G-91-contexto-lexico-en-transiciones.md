# G-91 — contexto léxico en las transiciones aprendidas

2026-09-27. Previo a código. G-89/G-90 siguen negativos y no se usan para QA.

## En palabras fáciles de entender

El modelo actual mira la clase de las palabras anteriores, pero pierde qué
palabra concreta había antes. Probaremos si los ejemplos humanos le permiten
usar también esa pista para distinguir nombres. No habrá una lista escrita
de palabras que indiquen lugares o personas: contará esas relaciones en los
textos de aprendizaje. Cuando no haya ejemplos suficientes, conservará más
peso de lo que ya sabía. Debe mejorar de forma medible en otros textos.

## Hipótesis y antecedente

G-90 redujo errores de formato sin mejorar F1. Esta prueba añade información
del texto, no más vetos de etiquetas. [Malouf, CoNLL 2002](https://aclanthology.org/W02-2019.pdf)
compara modelos de palabras, HMM y máxima entropía; una variante que añade
mayúsculas y palabra anterior sube F1 59,50→69,82. La ganancia no aísla esa
palabra ni demuestra esta adaptación: usa otra estimación y añade varias pistas.
Las revisiones recientes incompatibles de G-86/G-88/G-90 no justifican incluir
redes, anotaciones de LLM ni reglas semánticas manuales.

Reutilizar el decodificador, emisiones e interpolación G-89. Añadir un contexto
de conteo al mismo aprendizaje, con respaldo como los contextos G-32; no un
clasificador nuevo. Si funciona, se integra como respaldo contextual del
aprendiz existente solo después de las comprobaciones de transferencia.

## Diseño fijado

Mismo TRAIN humano CoNLL/UPC y modelo G-89, SHA
`7020a285adf4c9673c89ad0379f24735ca766d2f0da239e299113391f238d140`.
Contar etiqueta siguiente por `(etiqueta anterior,palabra anterior exacta)`;
incluir límites de secuencia con los símbolos ya usados por TnT. Conservar
todos los conteos, sin elegir palabras por significado o por `testa`.

Al decodificar, si P0 es la probabilidad de transición original, usar
`P=(conteo_siguiente + 8*P0)/(conteo_contexto + 8)` para el contexto observado.
Sin contexto, P=P0 exacto. Ocho es la fuerza de respaldo genérica G-24/G-32,
no se ajusta buscando F1. No sumar otra probabilidad independiente ni aplicar
el veto G-90. Procesar todos los tokens, con el mismo ancho de búsqueda.

Cuatro variantes: G-89 intacto; contexto léxico (principal); contexto que borra
la palabra y agrega solo por etiqueta previa; asignación de filas a palabras
equivocadas dentro de cada etiqueta previa, permutación semilla 1. Los dos
controles nuevos usan idéntica fórmula de respaldo. No leer nombres/prefijos
de etiquetas para decidir. La palabra previa y sus estados duran solo durante
una llamada; comienzo, fin y llamadas sucesivas se comprueban en focales.

## Evaluación y puertas

`testa` público ya gastado; una evaluación sin ajuste posterior. `testb` y
PAR-6 cerrados. Mismo evaluador G-89 de tramos exactos, clases, nombres completos
no vistos y tokens no vistos. Principal: F1 ≥0,67, ≥0,02 sobre G-89, ≥0,01
sobre cada control nuevo, recuperación ≥0,40 en ≥100 nombres completos nuevos.
Desactivación y recarga/hashseed 1 exactas. No pasar a QA si falla.

Si pasa, preregistrar comprobación separada humana `testb` antes de estudiar
preguntas/clases y utilidad en negocios. No confundir identificar nombres
en noticias con responder al usuario ni con un porcentaje de utilidad.

Reuso/aprendizaje ≤10 s CPU; evaluación/recarga ≤60 s, total ≤70 s, pared ≤100 s,
RAM conjunta ≤512 MiB. Contar modelo adicional, filas, palabras, respaldo,
CPU por etapa y latencia por secuencia, solo preparación futura de documentos.
Focales y trece rápidas; commit previo y `freeze-G91-prototipo`. Resultados
en `results_v3/g91_lexical_transitions.json`; motor/base estables intactos.
