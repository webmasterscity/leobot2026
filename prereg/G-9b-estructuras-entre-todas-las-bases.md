# G-9b — recurrencia y aprendizaje formal entre todas las bases

## Por qué es distinto de G-9

G-9 quedó rechazado porque una de ocho bases pequeñas tuvo 13/22 consultas con firma vista en las otras, frente a su umbral de 15. No se borra ese resultado. Aquellas ocho bases se habían elegido para poder ejecutar SQLite de tamaño reducido; la prueba **de estructura** no necesita SQLite. G-9b conserva exactamente la función `signature(sql)` de G-9, pero mide todas las 146 bases oficiales de enseñanza, sin elegir nombres ni descartar una base por resultado. La hipótesis es que una biblioteca de acciones de programa puede transferir entre dominios si las composiciones no triviales reaparecen ampliamente. Alternativa: la recurrencia se concentra en unas pocas bases o firmas triviales; entonces no construir un parser nuevo.

La idea de inducir acciones léxicas con un significado formal enseñado procede de [BabyDS, 2026](https://www.mdpi.com/2226-471X/11/5/99). Ese trabajo usa una gramática computacional y grounding diseñados; Leobot no recibe esos resultados ni usa una red neuronal. Enseñar SQL a Leobot cuenta como **instrucción**, mientras aprender una regla de composición que sirva en otra base contaría como **inducción/transferencia**. No confundirlo con aprender SQL desde respuesta sola.

## Puerta 0 preregistrada

Fuente `train_es.json` y hashes/revisión ya fijados en G-6; deduplicar SQL por base. Considerar elegible una base con ≥20 SQL distintos, criterio fijado antes de mirar su resultado. Mantener todas las bases elegibles, sin excepción por dominio. Firmas: exactamente la función de G-9, que registra aridad/agregadores de proyección, DISTINCT y presencia de unión, filtro, agregado, grupo, orden, límite, anidamiento y conjuntos, ocultando IDs/valores. «No trivial» requiere al menos dos acciones opcionales además de proyectar. Exigir:

1. ≥50 bases elegibles;
2. ≥30 firmas no triviales presentes en ≥3 bases;
3. en ≥70 % de bases elegibles, al menos 70 % de sus SQL distintos comparten firma con otra base;
4. ≥20 bases elegibles tienen ≥5 consultas con firma no trivial compartida por ≥3 bases.

Informar distribución, mínimo, p50, p95 y excepciones, no solo total. Puerta 0 usa SQL gold únicamente en evaluador; **no** enseña ni prueba Leobot. H0 debe ser idéntico antes/después. `PYTHONHASHSEED=0/1`. CPU ≤30 s, pared ≤60 s, RSS ≤256 MiB. Si falla, conservar resultado y descartar esta firma/fuente para G-9b; no retocar umbrales.

## Learner condicionado a puerta 0

Si pasa, congelar la implementación antes de escoger bases de comprobación por semilla derivada de H0. En tres particiones por bases completas, entregar pares pregunta española→SQL **solo de educación** mediante interfaz de demostración; la comprobación recibe pregunta y esquema, nunca SQL. Extraer operadores y restricciones de tipos del SQL enseñado; mantener hipótesis rivales de contribuciones de palabras/frases cortas, componer solo programas tipados y actualizar probabilidades/apoyo incrementalmente con presupuesto fijo. Prohibidos `eval`, ejecución de SQL generado en enseñanza y ramas por palabras/dominio. Comparar con `Language` de superficie exacta, G-7d de palabras sueltas, memoria exacta, fresco, mismas demostraciones sin composición y demostraciones barajadas. Incluir renombrado total, casos incompatibles, contraevidencia, persistencia y hash congelado.

Puerta 1: firmas **completas** correctas ≥60 % de consultas estructuralmente elegibles en cada partición, ≥15 puntos sobre mejor control, transferencia en ≥2 familias no isomorfas, sin errores seguros en incompatibles; ≤1 000 hipótesis por pregunta, CPU ≤120 s, pared ≤180 s, RSS ≤256 MiB, p95 compilado ≤10 ms. Medir costo de lectura, adquisición, búsqueda, validación, consolidación e inferencia y número de ejemplos. Si pasa, solo entonces abrir reserva final de bases/preguntas derivada del hash del motor y valorar integración en `Language` con regresión/latencia de 100 000 hechos. Firmas repetidas o aprendizaje desde SQL explícito **no** prueban comprensión documental ni AGI.
