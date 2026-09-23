# G-19 — ¿hay significado relacional reutilizable en el contexto léxico?

Fecha: 2026-09-23. Preregistro anterior al evaluador y a cualquier cambio de motor. H0 = `estable-E-1:leobot` = `1f3187f2ced4c97364503187d074815f33612326`.

## Decisión que cambia el ensayo

G-16 no pudo completar educación documental dentro de 120 s CPU; G-17/G-18 redujeron trabajo local pero no pasaron latencia. G-14 mostró que anclas literales alrededor de argumentos apenas cubren MASSIVE. La hipótesis distinta es que **rasgos distribuidos del texto entre dos entidades**, aprendidos de ejemplos independientes, permiten elegir una relación para pares nuevos. La alternativa sencilla es que solo el tipo de entidades, los nombres repetidos o la frecuencia de la relación explican cualquier acierto. Si el texto no vence esos controles, no integrar un clasificador léxico ni seguir optimizando el parser.

[Mintz y otros, 2009](https://aclanthology.org/P09-1113/) aporta el antecedente de rasgos textuales con supervisión distante, que advierte sobre ruido; [REDFM](https://aclanthology.org/2023.acl-long.237/) aporta una fuente real revisada por personas. Se revisaron publicaciones de 2026 sobre lectura simbólica; no se encontró en las fuentes consultadas un resultado que pruebe este mecanismo sin componentes neuronales en español. Ninguna capacidad de esos trabajos se atribuye a Leobot.

## Familia, datos y separación

Usar exclusivamente `train.es.jsonl` REDFM fijado en G-15, SHA-256 `3af0fff77d7bb3d2907839e1db8e33d56b8e84ae17309f056257f240ec8127b8`; `dev/test` oficiales permanecen cerrados. Repetir partición por artículos completos de G-15 con semillas 911/977/1039 derivadas de H0. **Educación**: párrafos con exactamente un triple y ambos tramos de entidad alineados; conservar solo pares separados por ≤160 caracteres sin `.?!` ni salto de línea entre ellos. Relaciones elegibles: ≥5 ejemplos de al menos 3 artículos de educación. **Reserva por artículo**: los mismos criterios estructurales, relación elegible y par de entidades no visto en educación. La elegibilidad se calcula sin mirar etiquetas de reserva, salvo comprobar pertenencia a relaciones elegibles al puntuar.

Este primer ensayo recibe del evaluador los **dos límites exactos de entidad también en reserva**. Es un techo de clasificación condicional, no extracción desde texto crudo ni aprendizaje de Leobot. No usar etiquetas de reserva para elegir rasgos, parámetros o umbral. Conservar agregados solamente, no textos de la fuente.

## Candidato y controles fijados

El evaluador construirá rasgos binarios sin nombres de entidades: palabras y parejas consecutivas **entre** las menciones (máximo 24 palabras), tres palabras antes de la primera y tres después de la segunda, y orden sujeto/objeto. Eliminar apariciones de las dos superficies de entidad de esos segmentos antes de extraer rasgos. Sin lemas escritos a mano ni léxicos por relación. Ponderar por frecuencia inversa de documento `1+log((N+1)/(df+1))`; para cada relación, promediar vectores de sus ejemplos, y elegir por similitud coseno. Empates exactos → abstención. No ajustar pesos después de mirar reserva. Este clasificador explícito es solo un candidato de mecanismo; el motor no lo leerá.

Comparar: tipo de entidad solamente (relación mayoritaria por par de tipos, desempate por frecuencia global); solo memoria (par de entidades idéntico), fresco (abstiene) y etiquetas de educación barajadas **dentro de cada par de tipos** con semilla fija. Medir también el estrato confundido de pares de tipos que admiten ≥2 relaciones en educación y tienen ≥20 casos elegibles en reserva, si existe; si no, declarar control insuficiente. Renombrar todas las superficies de entidad en una copia de entradas elegibles debe dejar idénticas las predicciones del candidato; si no, hay fuga léxica. Párrafos con varios triples son estructura incompatible y se reportan fuera de la puerta, sin convertirlos en negativos. El control de texto barajado, corrección de etiquetas, reinicio y promoción operacional quedan para el ensayo posterior **solo si** esta puerta de señal pasa; este inventario no mantiene creencias ni produce hechos.

## Métricas, umbral y presupuesto

Por semilla: número de ejemplos, relaciones, pares nuevos, tasa de abstención, exactitud top-1 del candidato y controles, matriz agregada de errores, aciertos por relación, CPU de carga/adquisición/predicción, pared, RSS y cantidad de rasgos. No inflar una relación recurrente como múltiples capacidades. La puerta exige en **cada una** de las tres semillas: ≥60 casos y ≥5 relaciones elegibles en reserva, exactitud ≥0,40 en pares nuevos, ventaja ≥0,15 puntos absolutos sobre **el mejor** de tipo, memoria y etiquetas barajadas, y al menos 5 relaciones con un acierto. En estrato de tipo confundido, si tiene ≥20 casos, exigir ventaja ≥0,10 frente a tipo y barajado; si no alcanza 20 en alguna semilla, esta puerta no acredita separación del confusor. La predicción tras renombrado debe ser idéntica. CPU ≤30 s, pared ≤60 s y RSS ≤128 MiB por semilla. H0 idéntico antes/después; repetir una semilla con `PYTHONHASHSEED=1` y exigir métricas discretas iguales. Si la semilla 911 falla, detener las otras para no repetir un diseño descartado. Ningún código del motor cambia en este ensayo; no se abre G-16 ni se crea tag por un simple techo positivo.

Si pasa, preregistrar integración en interfaces normales, inferencia de entidades sin límites externos, contraevidencia, persistencia, controles completos, latencia y reserva estructural adicional. Si falla, registrar qué señal faltó antes de proponer una representación diferente.

## En palabras fáciles de entender

Le daremos ejemplos de frases donde ya sabemos qué relación expresan dos nombres. Probaremos si las palabras que los rodean bastan para reconocer la relación entre nombres nuevos. Compararemos el resultado con usar solo el tipo de los nombres y con ejemplos mezclados. Si no mejora claramente, esta idea no entra en Leobot.
