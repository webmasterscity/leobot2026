# F-12 — separar sintaxis, relación y roles para recomponerlos

## Fallo, hipótesis y alternativa

F-10 promovió solo tres de 145 patrones y acertó 1/128; F-11 solicitó 100 triples reales según desacuerdo y no mejoró 1/128. La biblioteca interpreta cada superficie como un bloque: no puede reutilizar una estructura de frase aprendida con una relación y una expresión relacional aprendida en otra estructura. El DSL numérico `learner_dsl` tampoco admite secuencias tipadas; `language_acquisition._raw_lexical_meta_frames` solo cambia una posición léxica opaca. Hipótesis: **aprender por separado un marco con dos roles y un hueco relacional, y una correspondencia expresión→predicado**, validando cada componente, permite recombinaciones nuevas con el motor congelado. Alternativa: la semejanza de marcos se debe a palabras comunes y los límites de roles/relación siguen indeterminados. Si funciona, reemplazaría construcciones redundantes de superficie completa; si falla, no integrar un nuevo parser.

Un diagnóstico previo solo sobre enseñanza F-10 encontró 68 marcos exactos usados por al menos dos predicados con dos apoyos cada uno; 32 expresiones relacionales aparecían en dos marcos y 269 experiencias participaban en tales grupos. Esto hace viable un ensayo, **no prueba transferencia**. No usar esos identificadores como reserva final.

## Datos y partición

WebNLG 2020 original `train/1triples`, commit `587fa698bec705efbefe72a235a6019c2b9b8b6c`. Excluir del desarrollo los identificadores usados para F-6f/F-6g/F-7/F-8/F-10/F-11. H0 = `git rev-parse estable-E-1:leobot`. Seleccionar 128 textos humanos de desarrollo con entidades disjuntas por `sha256(H0 + ':F-12:web:' + id)`; 64 de validación interna sin entidades compartidas. Enseñar hasta 2 000 frases restantes con sus triples anotados. Codex no redacta casos ni traduce entradas. Además, crear una partición estructural de **combinaciones marco+expresión realmente presentes**: reservar hasta 64 entradas cuyo marco y cuya expresión existan por separado en enseñanza pero cuya combinación exacta no se enseñe. Los criterios de extracción y selección se fijan antes de mirar aciertos, con hash H0. Reportar ambos conjuntos por separado; si hay menos de 32 combinaciones estructurales elegibles, declarar este componente **no evaluable**, sin relajar la regla.

Reserva externa WebNLG `dev/2triples` únicamente tras pasar desarrollo y congelar el piloto. Exige composición de hechos; un acierto en un solo triple no la sustituye.

## Sustrato seguro

Piloto fuera del motor, Python estándar. Un programa declarativo contiene `literal`, `role(0)`, `role(1)` y `relation_span` de longitud 1–4; los roles tienen longitud 1–8. Generar marcos sustituyendo una frase relacional **observada**, nunca escrita por el desarrollador; seleccionar los compartidos por predicados distintos y respaldados por entidades independientes. Aprender la correspondencia expresión→predicado de episodios en al menos dos marcos. Al interpretar, enumerar como máximo 32 análisis, comprobar que todos los que sobreviven dan el mismo triple y abstenerse si discrepan. Validar límites de roles y predicado en ejemplos separados; contrastar con otras relaciones, participantes invertidos y señales auxiliares. Compilar un índice por literal discriminante; sin `eval`, Python generado, redes ni servicios inteligentes. Registrar episodios fuente y reconstruir dependencias al corregir.

Presupuesto: 64 marcos por orientación, 4 096 hipótesis totales, 120 s CPU, 180 s pared, RAM ≤256 MiB. Cada respuesta p95 ≤10 ms y tope 1 s. Medir adquisición, generación, validación, compilación, inferencia, persistencia, ejemplos y candidatos. Un marco que solo reconoce ejemplos enseñados no es transferencia.

## Controles y puerta

Tratamiento frente a F-6f y F-10 en las **mismas particiones**, ablación sin recombinación, fresco, solo memoria, misma información sin factorizar, predicados barajados, roles invertidos, relación incompatible, renombrado total, confusor lexical invertido, contraevidencia y reinicio. El motor mantiene H0. La intervención la aporta siempre el corpus; el sistema no inventa triples.

Puerta de desarrollo: ≥20/128 triples exactos con precisión ≥80 % y ≥5 más que ambas ablaciones; en la partición estructural ≥20/64 exactos con precisión ≥80 % y al menos cinco más que F-6f; ninguna promoción de programas falsos en etiquetas barajadas, cero afirmaciones seguras incompatibles, corrección/reinicio correctos, p95/costo bajo presupuesto. Si pasa un conjunto y falla el otro, no afirmar transferencia composicional ni integrar. No cambiar umbrales tras observar desarrollo; un nuevo diseño necesitaría otro preregistro.
