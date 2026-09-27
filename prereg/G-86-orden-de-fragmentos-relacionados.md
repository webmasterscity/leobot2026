# G-86 — aprender el orden de fragmentos relacionados

2026-09-27. Antes de código. Prototipo externo; motor
`11a1ef5836382d81a643cad0b217a8669ce0f2d1` y base del usuario intactos.

## En palabras fáciles de entender

Los ensayos anteriores aprendieron qué palabras suelen aparecer juntas, pero
muchos resúmenes que recibe el selector pierden su orden. Vamos a enseñarle
patrones cortos que conserven dónde aparecen las palabras conectadas entre la
pregunta y el texto. Aprenderá con preguntas y respuestas publicadas por personas;
nadie escribirá reglas sobre horarios, direcciones o negocios. Seguirá citando
el documento que se le cargue.

No sabemos si esto bastará. Compararemos el aprendizaje real con el mismo
material desordenado y con respuestas emparejadas incorrectamente. Si no mejora
las respuestas conservando la prudencia y la rapidez, guardaremos el resultado
negativo. Esta prueba no constituye una reserva nueva ni demuestra inteligencia
general por resolver ejemplos visibles.

## Investigación que cambia la decisión

- [Severyn y Moschitti, EMNLP 2013](https://aclanthology.org/D13-1044.pdf):
  representan pregunta y respuesta mediante estructuras sintácticas, marcando
  coincidencias entre ellas. Selección en TREC: MAP 0,6485 sin enriquecimiento
  semántico y 0,6781 con él. No es porcentaje de respuestas útiles. Usan SVM,
  analizadores y clasificadores; la correspondencia entre clases de pregunta
  y entidades incluye una tabla manual, que aquí se excluye. No demuestran
  menos de 5 ms en Python. Extraemos solo la conservación de fragmentos
  ordenados con marcas de relación.
- [Tymoshenko y Moschitti, EMNLP 2018](https://aclanthology.org/D18-1240.pdf):
  comparar preguntas con preguntas y respuestas con respuestas mejora algunos
  bancos; no todos. La parte de palabras sin redes obtiene MAP 67,67 en WikiQA
  test frente a 53,80 de similitudes internas simples; TREC no muestra esa
  ventaja. Excluyen preguntas sin respuesta en la evaluación limpia. También
  estudian representaciones neuronales y correspondencias manuales, excluidas
  aquí. G-66 ya aprendió productos léxicos: repetirlos no sería una idea nueva.
- [CoTu, julio de 2026, v1](https://arxiv.org/html/2607.14735v1): un modelo
  de 4B escribe programas para Z3/Python; presupuesto de 60 segundos y guía
  específica en instrucciones. No separa la comprensión simbólica de la red
  que traduce el texto. Se descarta como mecanismo operacional compatible.

## Hipótesis, antecedentes y piezas reutilizadas

Hipótesis: el orden local de clases de palabras y de sus conexiones aporta
evidencia que los conteos agregados PAR-2/G-84 omiten. Alternativa: son señales
de estilo, insuficientes para elegir evidencia en negocios nuevos.

F-18/F-19 aprendían inversiones o motivos globales sobre paráfrasis; G-48
requería caminos sintácticos desde respuestas anotadas; G-75 requería relaciones
de Predicate Matrix y participantes analizados. Aquí no se usa ese diccionario
ni árboles completos: se conservan secuencias de clases ya aprendidas en AnCora,
con coincidencias marcadas. G-85 añadió ejemplos a los mismos resúmenes y falló;
no se repite esa mezcla. El nuevo material solo enseña la señal estructural.

Se reutilizan `split_words`, `tag_words`, `_term`, puente G-78 y los conteos
`learn_weights` / `feature_score` de G-75. El selector y su calibración son PAR-2,
con G-84 directo como referencia. No se añade un nuevo método de aprendizaje.
Si aporta, sustituiría los conteos agregados redundantes solo tras una ablación;
no se integra por novedad bibliográfica.

## Educación y representación fijadas

Misma extracción MFAQ G-65, SHA
`c985eb099bcdadf87baa778786148e4de6c9a84057e68b4268ea2f832b884c66`:
≤100 pares por dominio, semilla 57 y exclusiones históricas. Pregunta ≤24
tokens, respuesta ≤48; rival siguiente distinto del mismo dominio, orden
lexicográfico circular. Ordenar por SHA de `(dominio,pregunta,respuesta)` como
G-75 y tomar hasta **6 000** pares. Excluir rivales que excedan 48 tokens.

Para cada pareja, conservar los tokens completos y sus clases AnCora. Marcar
cada posición por coincidencia directa de lema, enlace del puente G-78 ya
aprendido o ausencia; la directa tiene precedencia. Los signos tienen lema
vacío y no se enlazan por igualdad. No modificar ni reenseñar ese puente.
Los títulos no se incluyen en la nueva señal: representan contexto heredado,
ya considerado por las variables originales, no el orden de la frase citada.

Representar cada token como `(clase,marca)`. Añadir límites de comienzo/final
y contar presencia de fragmentos contiguos de longitudes 1, 2 y 3, separados
por lado pregunta/respuesta. Los fragmentos de respuesta se condicionan por
la secuencia de interrogativas reconocidas en la pregunta mediante el inventario
ya aprendido de AnCora (formas normalizadas); ninguna lista escrita aquí.
No conservar palabras de contenido, nombres, valores ni frases en el modelo.

Contar fragmentos en respuestas propias y rivales con G-75: apoyo en ≥5
dominios, peso `log((propias+1)/(rivales+1))`, máximo 200 000 candidatos.
Sin búsqueda de parámetros. Ordenar todas las operaciones para independencia
de hash. Tres tablas: orden real; orden borrado (ordenar los tokens marcados
por clase/marca antes de formar fragmentos, conservando límites); señal confundida
(G-75, semilla 75, intercambio propio/rival por pareja). Las tres usan iguales
ejemplos, cortes y conteos. El control sin señal conserva G-84 directo exacto.

En respuesta: preparar tokens/clases de cada unidad al cargar contexto. Etiquetar
la pregunta en cada llamada, sin memoria de preguntas. Máximos 24/48 también
en uso; ante exceso la señal devuelve cero y registra exclusión. Obtener los
fragmentos solo para las seis candidatas existentes; no cambiar su inventario.
Para cada longitud añadir puntaje G-75 normalizado y diferencia contra el mejor
rival entre esas candidatas: seis variables, intervalos de margen PAR-2 ya
existentes. Esas variables se suman a las 33 de G-84 directo; ninguna decisión
semántica fija. Preparación de documentos y preguntas incluida en los costos.

## Medición, controles y puertas

Selector enseñado solo con TRAIN G-68 (3 520 turnos); calibración cruzada por
negocio, isotónica con empates de G-68, seis candidatas y umbral 0,4. Ni las
preguntas del usuario ni DEV enseñan tablas o eligen parámetros. Evaluación
única en DEV G-62/G-63/G-64 gastado, mediante `Bot.answer` con historial real.

Principal frente a sin señal, orden borrado y etiquetas confundidas. Debe:

- alcanzar ≥344/816 útiles y ≤73/488 citas sin dato;
- elegir bien ≥499/816 antes de abstención;
- sumar ≥17 útiles frente a cada control (incluido sin señal);
- producir cero evidencias no literales; p95 y máximo <5 ms;
- reproducir referencia exacta, desactivación y recarga en proceso nuevo,
  `PYTHONHASHSEED=1`, con JSON compacto ≤100 MiB, sin descartar datos.

No basta citar para ser útil; estas claves no sustituyen juez de engaño. Bot
fresco sin señal se cubre por desactivación; no es capacidad desde cero porque
se reutiliza AnCora/G-78. Memoria de respuestas no existe en estas tablas;
misma información se cubre por orden borrado. Retirar tabla debe restaurar
exacta la referencia; renombrado de símbolos con clases/puente transportados
debe conservar fragmentos en prueba focal. Cambiar documento no puede conservar
sus fragmentos. Controles externos, reserva de otros negocios, juez y auditor
5.10 solo tras pasar desarrollo y congelar integración. PAR-6 ajeno permanece
cerrado. Si falla, no aumentar ventanas/muestra ni mover umbral con DEV.

## Presupuesto y ejecución

Un proceso pesado. Enseñanza ≤600 s CPU; evaluación/controles ≤240 s;
total ≤840 s CPU, pared ≤1 100 s, RAM conjunta ≤1 GiB. Contabilizar separadamente
selección de ejemplos, preparación, conteos, ajuste del selector, comprobación,
guardado/compactación y recarga. Registrar intentos fallidos; progreso y punto
de recuperación tras enseñanza. No descargas de datos nuevas.

Pruebas focales de orden, renombrado, exclusión por longitud, recambio de
contexto y desactivación. Trece rápidas del motor por ciclo. Commit de este
preregistro antes del código; `freeze-G86-prototipo` antes de medir. Resultados
en `results_v3/g86_ordered_fragments.json`; modelos candidatos fuera de `leobot/`.
