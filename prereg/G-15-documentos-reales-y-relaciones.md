# G-15 — puerta para aprender relaciones desde documentos reales

Fecha: 2026-09-23. Preregistro anterior al código. H0 `estable-E-1:leobot` = `1f3187f2ced4c97364503187d074815f33612326`. G-13/14 rechazaron pistas locales y anclas literales para límites de fragmentos en órdenes localizadas. El siguiente experimento vuelve a texto documental, donde las entidades y los hechos pueden anclarse a un mundo verificable sin respuestas escritas por otra IA.

## Fuente y pregunta

Usar exclusivamente [`train.es.jsonl` de REDFM](https://huggingface.co/datasets/Babelscape/REDFM/blob/7fab33bee528dc1dd09d90f788afc93d35fd71b3/data/train.es.jsonl), revisión fija `7fab33bee528dc1dd09d90f788afc93d35fd71b3`, sin abrir `dev/test`. [REDFM](https://aclanthology.org/2023.acl-long.237/) procede de Wikipedia y Wikidata y fue filtrado por personas; sus triples no son infalibles ni equivalen a comprensión de un documento. La ficha del dataset indica CC BY-SA 4.0, mientras el repositorio del proyecto menciona CC BY-SA-NC 4.0 para código; registrar la diferencia y conservar solo métricas agregadas, sin republicar texto.

Fallo observado: el lector de `leobot/document.py` puede organizar hechos, referencias y contradicciones **después** de interpretar oraciones, pero E-7 obtuvo 0/40 extracciones literales en textos nuevos y G-13 no aprendió límites nuevos. Hipótesis de fuente: hay suficientes documentos españoles con entidades alineadas y relaciones repetidas para probar si experiencias estructuradas permiten adquirir construcciones reutilizables y luego extraer hechos sobre entidades no enseñadas. Alternativa: anotaciones escasas, entidades no alineadas o relaciones demasiado dispersas impiden ese ensayo; en tal caso no programar un learner sobre REDFM.

## Inventario preregistrado

Descargar solo ese archivo (≤10 MiB, ≤30 s de pared) y registrar SHA-256, bytes, filas, documentos distintos, relaciones y entidades. Agrupar por `uri` de artículo para evitar que párrafos de la misma página crucen enseñanza y comprobación. Para semillas 911/977/1039, barajar `uri` con primeros ocho dígitos de H0 XOR semilla XOR `0x69B`; excluir `max(20, round(0.2*n))` artículos completos. Procesar todas las filas y triples del archivo de enseñanza; no elegir por tema ni facilidad. Una mención es alineada si `text[start:end]` coincide con `surfaceform` al ignorar mayúsculas; reportar fallos, no repararlos manualmente.

Una relación es enseñable si tiene ≥20 artículos independientes de enseñanza. La puerta de fuente pasa **en cada** semilla si hay ≥500 párrafos de enseñanza, ≥100 de comprobación, ≥5 relaciones enseñables que aparezcan además en ≥10 artículos excluidos, al menos 50 % de triples excluidos tienen relación enseñable, y ≥95 % de menciones de sujeto/objeto están alineadas. Medir también cuántas filas tienen un único triple frente a varios y cuántos pares de entidades aparecen con relaciones rivales, para planear confusores. Repetir con `PYTHONHASHSEED=0/1`, exigir conteos iguales; CPU ≤10 s, pared ≤30 s, RAM ≤128 MiB. H0 antes/después.

Esta puerta es **solo viabilidad de fuente**: no enseñar triples aún, no leer la respuesta de la comprobación durante aprendizaje, no atribuir extracción a Leobot. Si pasa, preregistrar aparte ensayo de educación por interfaces normales: hechos estructurados disponibles en episodios de enseñanza, documento crudo para aprender, documentos y entidades nuevos como comprobación; ablar documento manteniendo los mismos hechos, barajar relaciones dentro de artículo, memoria, fresco, contraevidencia, reinicio, CPU total y latencia. Una futura ventaja por recordar los triples enseñados no contará como lectura.

## En palabras fáciles de entender

Buscaremos textos reales que mencionen personas, lugares u otras cosas y digan cómo se relacionan. Primero comprobaremos si las marcas de esas relaciones son fiables y si hay suficientes ejemplos distintos para enseñar y evaluar. Tener buenos ejemplos no significa que Leobot ya sepa leerlos.
