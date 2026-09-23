# G-16 — ¿aprende el motor congelado a leer hechos en Wikipedia?

Fecha: 2026-09-23. Preregistro anterior al evaluador. H0 = `estable-E-1:leobot` = `1f3187f2ced4c97364503187d074815f33612326`. La puerta de fuente [G-15](G-15-documentos-reales-y-relaciones.md) pasó tras corregir un error de lectura de esquema; eso no acredita ninguna capacidad de Leobot.

## Fallo e hipótesis

E-7 obtuvo 0/40 respuestas literales en textos nuevos. `ingest_document_text` organiza hechos una vez que hay una construcción reconocida, pero no crea significados fiables de frases nuevas. Hipótesis: con hechos explícitos y ejemplos de frases emparejadas con esos hechos, la `Language` existente aprende construcciones que después extraen hechos **nuevos** de artículos no enseñados. Alternativa: solo memoriza textos o hechos previos; el bot con idénticos hechos y documentos sin emparejamiento rendirá igual. Si la hipótesis falla, no añadir una variante de extracción basada en frases exactas.

## Datos y educación permitida

Solo [`train.es.jsonl` REDFM](https://huggingface.co/datasets/Babelscape/REDFM/blob/7fab33bee528dc1dd09d90f788afc93d35fd71b3/data/train.es.jsonl), SHA-256 `3af0fff77d7bb3d2907839e1db8e33d56b8e84ae17309f056257f240ec8127b8`. Dividir artículos completos por `uri` con H0 y semillas 911/977/1039 como G-15; `dev/test` oficiales y `dev_es` cerrados. Conservar todos los párrafos/triples excluidos en el evaluador y proporcionar **solo texto crudo** en el ensayo. Datos de enseñanza: hechos `P... (sujeto, objeto)` provenientes de todos los párrafos de artículos de educación; texto crudo de esos párrafos; y, para párrafos con exactamente un triple, una instrucción explícita `frase ↔ marco` si ambos argumentos aparecen en una misma oración segmentada por el motor. Seleccionar esa oración por posiciones de entidad dadas **solo en enseñanza**; si es ambigua, larga o `Language.teach` la rechaza, contar el rechazo y no repararlo. Esto es instrucción supervisada, no invención autónoma de semántica.

Usar `Bot.ingest`, `Bot.language.teach` y `Bot.ingest_document_text`, sin cambiar `leobot/`. El bot de tratamiento y la ablación reciben los **mismos hechos** y **todos los mismos documentos de educación**. Solo el tratamiento recibe el emparejamiento explícito. Control de papeles mezclados: mismos argumentos y oración, pero permutar predicados entre ejemplos con el mismo par de tipos de entidad; mantener los hechos correctos para igualar información, y enseñar los marcos permutados. Solo memoria: hechos, sin texto. Fresco: sin educación. Se contabilizan frases instruibles, construcciones aceptadas, rechazos y costo. Ningún gold de artículo excluido entra en esos bots.

## Ensayo y controles

Guardar y cargar tratamiento al terminar educación; verificar que sobrevive una pequeña sonda de las mismas frases enseñadas. Después entregar en orden fijo **todos** los párrafos excluidos mediante `ingest_document_text` a tratamiento, ablación, mezclado, memoria y fresco. Un acierto requiere que el hecho con predicado y dos argumentos normalizados aparezca por primera vez en la memoria **con procedencia del artículo excluido**; recordar el mismo triple de educación no cuenta. Reportar por separado párrafos con un único triple y todos los triples, y pares de entidades nuevos frente a educación. Un hecho nuevo sin relación en el conjunto gold de ese párrafo es falso positivo observable; los triples del corpus pueden ser incompletos, así que esta precisión es una aproximación conservadora, no certificación ontológica.

Control de incompatibilidad: artículos con varias relaciones no se excluyen de resultados; se miden como estrato estructural diferente. Control confundido: predicado mezclado dentro de par de tipos, no barajado global. Reinicio obligatorio; medir si cambiar entidades por nombres opacos en una muestra de párrafos de prueba conserva hechos solo como diagnóstico, sin pasarle etiquetas al motor. Si hay éxito de cobertura, ejecutar contraevidencia con una corrección explícita de un hecho promovido y comprobar retirada y persistencia; si no hay hechos promovidos, registrar que no aplica. H0 antes/después de cada ensayo.

## Puerta y presupuesto

En **cada** semilla, se exige ≥20 % de triples **nuevos** correctos en párrafos con un triple, ≥5 % de todos los triples nuevos, ≥10 puntos de ventaja sobre el mejor entre ablación/mezclado/memoria/fresco y al menos cinco predicados distintos con hechos nuevos correctos. Precisión observable ≥80 % entre hechos `P...` creados a partir de artículos excluidos. Guardar/cargar y H0 pasan. CPU total ≤120 s, pared ≤180 s y RSS ≤256 MiB por semilla; lectura de cada documento ≤1 s y p95 de interpretación ya educada ≤10 ms, sin aumentar presupuestos. Si la primera semilla falla por calidad o costo, registrar el fallo y detener las otras dos para no repetir un diseño descartado; no cambiar umbrales. Ejecutar las pruebas rápidas; regresión completa solo si se pretende un tag estable.

Un ensayo fallido aquí no refuta toda la lectura ni la educación desde documentos: refuta la ruta actual de frases completas emparejadas y su extrapolación en REDFM. Un ensayo exitoso todavía no prueba comprensión abierta: necesita controles en otras fuentes, lengua natural nueva, corrección, escalabilidad e integración antes de afirmaciones generales.

## En palabras fáciles de entender

Le enseñaremos algunos hechos junto a las frases de Wikipedia que los expresan. Después leerá artículos distintos y veremos si descubre hechos que nadie le entregó antes. Si solo recuerda los hechos enseñados, los otros bots con la misma información lo dejarán en evidencia.
