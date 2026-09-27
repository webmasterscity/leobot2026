# G-93 — clases amplias aprendidas de respuestas humanas

2026-09-27. Previo a descarga adicional, código y medición.

## En palabras fáciles de entender

Una palabra puede referirse a un lugar, una cosa o una actividad. Leobot ya
aprende clases gramaticales, pero no basta con saber que algo es un sustantivo.
Probaremos si un diccionario público y preguntas con respuestas escritas por
personas permiten aprender distinciones más útiles. El programa contará qué
clases aparecen en las respuestas a cada forma de pregunta. Nadie escribirá
una correspondencia entre una pregunta concreta y la respuesta que debe dar.
Las respuestas seguirán saliendo del texto del negocio. Se medirá también
si esta ayuda lo lleva a citar algo cuando falta el dato pedido.

## Motivo, fuentes y límites

[Chang y colaboradores, 2009](https://aclanthology.org/O09-1016.pdf) enseñan un
clasificador con clases de respuestas obtenidas de WordNet y de Wikipedia.
En su comparación inglesa, WordNet pasa de 34 % a 42 % en primera respuesta;
ampliarlo con Wikipedia llega a 44 %. Usan búsqueda web, ejemplos de concursos
y máxima entropía; no prueban abstención, español ni el costo de nuestro kiosco.
Se toma la idea de **enseñar pregunta/clase mediante respuestas**, no sus cifras
ni su sistema completo. WordNet es conocimiento humano externo, no clases
descubiertas desde texto sin etiquetas; el aprendizaje de la relación con las
preguntas sí lo hace el programa contando ejemplos.

[Marton y colaboradores, 2005](https://projects.csail.mit.edu/csw/2005/proceedings/marton_csw05.pdf)
usan patrones escritos y obtienen alrededor de 50 % de precisión en relaciones;
su propuesta no demuestra QA completo. No copiar esos patrones.
[McNamee y colaboradores, 2008](https://ai.stanford.edu/~rion/papers/nehypes_ijcnlp08.pdf)
necesitan 17,3 millones de pares y revisión humana adicional; no incorporar su
extracción de relaciones. La búsqueda reciente también halló
[un trabajo de marzo de 2026](https://doi.org/10.1016/j.engappai.2026.114011)
que usa redes de grafos y modelos de lenguaje: queda excluido.

G-34 solo usó compartir sentidos como coincidencia; G-43 usó clases gramaticales;
G-76 indujo temas de documentos. Esta prueba usa clases amplias del diccionario
para representar **el tramo humano de respuesta**, y aprende qué pide una pregunta.
G-91/G-92 no se utilizan: su comprobación separada falló. No reabrir `testb`.
Si funciona, la señal podrá sustituir la clase gramatical del selector, previa
ablación; no crear otro aprendiz general ni otra ruta de respuestas.

## Datos y decisión fija

- Diccionario español ya usado en G-34: `omwn/omw-data`, revisión
  `406bf83b3c507a3d1f26e88252d5d66893fd36bf`, `wns/mcr/wn-data-spa.tab`, SHA
  `0ec37ce94ee2acc63ad6b120e1051f9841d172778cc24adc0023fb8dccf0a7cd`.
- Clases de sustantivos de WordNet 3.0 oficial:
  `https://wordnetcode.princeton.edu/3.0/WordNet-3.0.tar.gz`, miembro
  `WordNet-3.0/dict/data.noun`. Formato en
  [documentación original](https://wordnet.princeton.edu/documentation/lexnames5wn).
  Asociar id español de sentido con offset y número de archivo de esta misma
  versión. Ignorar definiciones inglesas y nombres legibles de las clases.
- Descargar cada fuente con límite 30 s/20 MiB; registrar huellas, tamaño,
  licencia y tiempo antes de congelar. Si falla o el español no coincide con
  su huella histórica, detener la adquisición; no cambiar de versión.
- Usar las 10 000 preguntas humanas SQAC TRAIN de `g85.select_human`, idénticas
  a G-78, sin nuevos ejemplos ni desarrollo/test oficiales. Semántica por
  respuestas cortas humanas, no por texto que las rodea ni por claves del kiosco.

Normalizar palabras con separación y lemas aprendidos del bot, más `_plain`.
Solo entradas de una palabra; excluir expresiones de varias palabras sin
asignar sus sentidos a cada componente. Conservar todas las clases posibles
de cada palabra; no elegir un sentido a mano. Cada palabra distinta aporta
masa uno repartida entre sus clases, y la distribución del texto se normaliza.
No hay tabla por tema, negocio o tipo de pregunta en el código.

Para cada clave de `_kind_keys` existente, acumular las distribuciones de las
respuestas con algún miembro conocido. Conservar número de ejemplos y suma
por clase. Consulta: clave más específica con `KIND_SUPPORT` existente; dividir
por suma de masas, sin elegir una sola clase ni ajustar corte con desarrollo.
Es reutilización de conteos pregunta/clase, sin otro clasificador.

Comparar cuatro variantes con mismo selector PAR-2/G-84 directo y seis candidatas:
sin señal, clases del diccionario, clases gramaticales, preguntas confundidas.
Control gramatical cuenta los tags aprendidos de la respuesta con `tag_words`;
control confundido permuta filas completas de pregunta/clase entre claves,
semilla 1. Registrar cobertura de cada educación; la gramatical puede disponer
de más ejemplos por la falta de palabras del diccionario. No ocultar esa diferencia.

## Representación y medición

Las 33 variables y propuestas de G-84 directo siguen iguales. Preparar clases
de cada unidad en `load_context`, usando su propio texto, sin encabezado heredado.
Agregar cuatro variables: disponibilidad de distribución de pregunta; producto
escalar pregunta/unidad; margen frente a mejor otra unidad; proporción de
palabras conocidas en la unidad. Bins existentes `COVER_BINS` para producto y
proporción, `SELECTION_MARGINS` para margen. Sin señal devuelve las 33 originales.
El control gramatical usa clases ya calculadas de unidad; disponibilidad 0 si
no hay distribución. Todas las tablas son datos guardables; no guardar ejemplos.

Misma educación del selector: seis bancos TRAIN, 3 520 turnos, partición por
negocio, L2=1, hasta 25 iteraciones, tolerancia 1e-6, calibración fuera de la
mitad entrenada con empate G-68, cita desde 0,4. Guardar modelos antes de DEV.
Reproducir huellas de base estable y G-84 directo; retirar señales/restaurar;
reinicio en proceso nuevo/hashseed 1 con base completa compacta <100 MiB.
Medir DEV G-62/63/64 gastado, selección cruda y respuestas reales, costo de
preparar documento, p50/p95/máximo. No usar panadería, PAR-6 ni duxiV2.

Puertas del ensayo: ≥368/816 útiles (al menos +41 sobre G-84 directo),
≤73/488 citas sin dato, ≥491/816 elecciones correctas, ≥17 útiles sobre cada
control gramatical/confundido, cero citas no literales, desactivación y reinicio
exactos, p95 y máximo <5 ms. No bajar criterios después de observar resultados.
Una aprobación parcial no satisface por sí sola la meta final de ≥60 % de
respuestas útiles con juicio independiente, reserva nueva y revisión del motor.

Presupuesto: adquisición ≤60 s pared; enseñanza/preparación ≤600 s CPU;
evaluación, guardado y recarga ≤200 s; total ensayo ≤800 s, ≤1 000 s pared;
RAM conjunta ≤1 GiB. Incluir adquisición y costos previos reutilizados por
separado. Una ejecución pesada. Registrar interrupciones con costo.
Pruebas focales: clase desconocida, ambigüedad conservada, renombrado de clases,
ausencia de información, sustitución de documento y desactivación. Trece rápidas.
Congelar `freeze-G93-prototipo` antes de medir. Sin cambios en `leobot/` ni base estable.
