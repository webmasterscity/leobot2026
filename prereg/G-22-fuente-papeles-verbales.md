# G-22 — puerta de fuente para papeles verbales en español

Fecha: 2026-09-23. Preregistro anterior al evaluador y a abrir los datos. Motor H0 `1f3187f2ced4c97364503187d074815f33612326`.

## Por qué cambiar de experiencia

G-19/G-20: el texto alrededor de entidades no superó al tipo de entidades. G-21: 45 fragmentos con apoyo en educación cubrieron 5/75 pares nuevos e igualaron al control léxico en esos cinco. REDFM asocia relaciones a párrafos, pero no señala qué palabra de la frase expresa la relación ni qué tramo tiene cada papel. Seguir agregando trozos literales no resuelve esa falta de estructura. Hipótesis de **fuente**: [UP Spanish AnCora](https://github.com/UniversalPropositions/UP_Spanish-AnCora) y [UD Spanish AnCora](https://github.com/UniversalDependencies/UD_Spanish-AnCora) ofrecen suficientes oraciones reales con predicado y argumentos alineados para estudiar inducción de operaciones léxicas y transferencia entre verbos. Alternativa: la alineación es incompleta/ruidosa o los papeles no recurren entre lemas; cambiar la fuente no ayudaría. Si pasa, solo autoriza preregistrar un learner, no acredita capacidad de Leobot.

Fijar revisión UP `7a03859143e52c57f94a8c0480c0e6d433f6a91f` y UD `20adddbfcdd773c6dc97ba48ea11ca9364e74185`, obtenidas de HEAD antes de este preregistro. Descargar **solo** `es_ancora-up-train.conllup` y `es_ancora-ud-train.conllu` desde esas revisiones. No abrir `dev/test`. Registrar SHA-256 y tamaños de los dos archivos en el resultado. La documentación UP declara columnas de sentido, cabeza y tramo de argumentos y advierte sobre errores de alineación y transferencia de papeles; ninguna correspondencia se asumirá perfecta. Por prudencia de licencias, conservar solo métricas agregadas en el repositorio, sin republicar oraciones.

## Puerta estructural y presupuesto

Leer ambos formatos por `sent_id`; comprobar ID único, coincidencia de secuencia de IDs de tokens, token predicado presente, cabeza y extremos de argumento presentes, `start ≤ end` y mismo número de tokens en oraciones pareadas. Registrar sentencias sin par, duplicadas, predicados, tramos, papeles, lemas, sentidos y fallos por categoría. No reparar ejemplos manualmente. Una prueba de transferencia futura requiere al menos **3 papeles** que aparezcan cada uno en ≥20 lemas verbales distintos y ≥100 predicados, y ≥100 lemas totales. Puerta de fuente: ≥5000 oraciones pareadas con texto UD, ≥1000 predicados anotados, ≥5000 argumentos, ≥95 % de sentencias UP emparejadas con IDs de tokens idénticos, ≥90 % de argumentos con tramos y cabezas válidos, y la recurrencia anterior. El evaluador no etiquetará semánticamente nuevas oraciones; solo contará anotaciones de la fuente.

Límites: ≤20 MiB de UP y ≤40 MiB de UD, CPU ≤15 s, pared ≤45 s y RAM pico ≤128 MiB. Repetir `PYTHONHASHSEED=0/1` y exigir conteos idénticos; motor H0 y evaluador congelados durante ambas lecturas. Si falla, registrar el motivo y no diseñar un learner sobre esta fuente. Si pasa, preregistrar por separado el aprendizaje de fragmento→papel y verbo→operador, con held-out por documento/lema, controles por lema y tipo, renombrado, corrección, reinicio, CPU y latencia. No promover mecanismo, abrir reserva final ni crear tag por una simple puerta de fuente.

[BabyDS, 2026](https://researchportal.hw.ac.uk/en/publications/babyds-visually-grounded-grammar-induction-with-online-curriculum/) motiva separar acciones léxicas aprendidas de la estructura semántica ofrecida; sus demostraciones ocurren en un mundo acotado y no prueban lectura abierta en español. No se adoptará su arquitectura completa por analogía.

## En palabras fáciles de entender

La fuente anterior decía qué relación había en un párrafo, pero no mostraba qué partes de la frase hacían cada trabajo. Revisaremos una colección de oraciones españolas que sí marca esos papeles. Si las marcas son suficientes y coinciden con las frases, podremos probar otra forma de aprender; esta revisión por sí sola no enseña nada nuevo a Leobot.
