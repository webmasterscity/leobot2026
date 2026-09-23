# G-14 — puerta de construcciones con huecos entre ámbitos

Fecha: 2026-09-23. Preregistro anterior al código. H0 `estable-E-1:leobot` = `1f3187f2ced4c97364503187d074815f33612326`. G-13 falló en tres particiones: F1 de fragmento+papel 0,339/0,228/0,079; para valores nuevos 0,042/0,027/0,015. Su diagnóstico posterior da un techo de F1 de límites de fragmento de solo 0,407/0,278/0,134 aun si los papeles fueran perfectos. Hace falta discriminar si pueden aprenderse **construcciones reutilizables que delimiten el hueco**, antes de programar otra búsqueda.

## Hipótesis, alternativa y fuente

Hipótesis: una pareja de palabras fijas alrededor de un fragmento anotado identifica un papel y los límites de un valor variable, y ese patrón aparece en varios ámbitos. Alternativa: los contextos son propios de cada ámbito o no bastan para separar papeles; repetir una construcción exacta no ayudará. Los [léxicos factorizados CCG](https://research.google/pubs/lexical-generalization-in-ccg-grammar-induction-for-semantic-parsing/) y [BabyDS 2026](https://www.mdpi.com/2226-471X/11/5/99) motivan buscar piezas reutilizables, pero no validan este patrón sencillo.

Fuente fijada: MASSIVE 1.1 español `train`, miembro SHA-256 `310462a79fa181ff83c643a8d356c7b8155fd37a25e80a77ba3ca9b29305c4a5`; los oficiales `dev/test` permanecen cerrados. Usar las mismas particiones por 18 ámbitos y semillas 719/787/853 derivadas de H0 que G-12/13. Los papeles son elegibles solo si tienen ≥20 ejemplos en ≥3 ámbitos de enseñanza. Valores nuevos = secuencia de palabras del fragmento ausente de todos los fragmentos positivos de enseñanza de papeles elegibles.

## Inventario y control

De cada fragmento anotado de 1–6 palabras extraer, sin nombres de dominio ni verbos escritos a mano, dos tipos de contexto: una o dos palabras inmediatamente a izquierda y a derecha; usar marcas universales de inicio/fin si falta un lado. Clave de patrón = (longitud del contexto, palabras izquierda, palabras derecha). Contar ejemplos por papel, frases independientes y ámbitos de enseñanza. Promover para este **inventario** una clave solo si aparece en ≥8 frases de ≥3 ámbitos, su papel más frecuente concentra ≥90 % de todos los fragmentos anotados de enseñanza con esa clave y hay un único ganador. Guardar también patrones rivales e impuros; no usarlos como respuesta.

Control confundido: dentro de cada ámbito de enseñanza, barajar papeles entre fragmentos mientras se conservan texto, fronteras y distribución de papeles. Aplicar exactamente el mismo inventario. El evaluador usa los fragmentos de ámbitos excluidos solo **después** de congelar ambos inventarios: mide cuántos fragmentos con papel elegible poseen una clave promovida con papel correcto. Contar todos y los de valor nuevo; no filtrar preguntas fáciles. Esto es un **techo de cobertura con límites entregados por el evaluador**, no una predicción desde texto crudo.

Puerta para justificar un aprendiz posterior, en **cada** semilla: ≥5 patrones promovidos, cobertura correcta de ≥40 % de fragmentos elegibles, ≥25 % de fragmentos elegibles con valor nuevo, y ventaja de ≥20 puntos sobre etiquetas barajadas tanto en todos como en valores nuevos. Si falla, no implementar un parser de anclas exactas; el siguiente diseño deberá inducir clases de construcciones o usar evidencia adicional, sin fingir que más patrones resuelven el texto libre. Si pasa, preregistrar aparte la búsqueda desde texto crudo, negativos, ambigüedad, contraevidencia, reinicio y latencia; esta puerta no prueba aprendizaje ni comprensión.

Inventario CPU ≤15 s, pared ≤60 s y RAM ≤256 MiB por ejecución; repetir con `PYTHONHASHSEED=0/1` y exigir conteos idénticos. H0 antes/después. No procede medir latencia de respuesta ni persistencia porque aquí no habrá aprendiz operacional. Conservar cualquier fallo de fuente/red separado de un fallo del mecanismo.

## En palabras fáciles de entender

Buscaremos frases que rodean un dato y sirven para reconocer dónde empieza y acaba. Comprobaremos si esas formas aparecen en varios ámbitos y también alrededor de datos nuevos. Si casi nunca se repiten, copiar más patrones de la misma clase no solucionará el problema.
