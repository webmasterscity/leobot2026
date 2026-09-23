# G-27 — preguntar desde relaciones inducidas de texto crudo

Fecha: 2026-09-23. Preregistro previo al cambio. Base estable `estable-G-1:leobot` = `0c5f3152b3c93273c25d4108e7b73bba0629d804`.

## Fallo, hipótesis y alternativa

G-26b requirió `allow_extensional_grounding=True` y hechos predicativos ya dados. Sin esa opción, el motor puede inducir dos relaciones opacas desde tres frases crudas cada una, aprender sus hechos y una negación explícita, pero una frase desconocida que coincide con ambas queda como `concept_pending`: no entra en la versión espacial ni produce pregunta. Se reprodujo con dos verbos distintos y «Ana protege Luis»/«Bea protege Mario»; llamar al recolector existente directamente sí produjo dos hipótesis y propuso «¿Es cierto que Dana protege Ciro?». Hipótesis: permitir en la ruta normal **solo la recolección de ≥2 hipótesis compatibles**, sin promoción por coocurrencia y exigiendo respuesta a una pregunta con verdad/falsedad explícitas, cierra este ciclo. Alternativa: la inducción cruda genera anclas inestables y la pregunta no transfiere; entonces no integrar.

No se agrega un learner ni una lista de verbos. Se reutilizan antiunificación cruda, versión espacial, MetaController y retiro G-26b. La [investigación primaria sobre anclaje de estructuras lingüísticas, 2025](https://ojs.aaai.org/index.php/AAAI/article/view/35119) apoya buscar señales externas; el [trabajo de clarificación estructurada de 2026](https://aclanthology.org/2026.findings-acl.2028/) usa LLM y solo aporta la pregunta experimental, no su mecanismo neuronal.

## Experiencia, controles y reserva

Desarrollo visible: dos relaciones de superficie con tres parejas cada una, dos frases de una tercera superficie con las mismas parejas, una pareja donde la primera relación es verdadera y la segunda está explícitamente negada con «no». Todo se entrega mediante `Bot.respond` sobre **texto natural**, sin `ingest`, JSON, `Atom`, frame ni predicado suministrado al bot. El entorno responde sí/no solo después de la propuesta; nunca se fabrica la respuesta dentro del motor.

Evaluación: 12 familias con vocabulario, entidades y orden de roles nuevos; semilla de los primeros ocho dígitos de `git rev-parse <commit>:leobot`, generada tras congelar motor y evaluador. Mitad de los significados verdaderos corresponden a cada relación. En educación ambas relaciones coinciden perfectamente; en la pregunta se invierte esa coincidencia con negación explícita. Control tratamiento frente a la ruta G-1 sin recolección segura; fresco sin frases; solo memoria/misma información sin inducción; estructura incompatible o sin negación; renombrado total; respuesta contradictoria y retiro de hechos derivados; guardar/cargar antes y después. No exigir al sistema descubrir verdad por ausencia de hechos.

Puerta: ≥10/12 familias inducen dos raíces crudas y mantienen la tercera frase como dos hipótesis **sin promoverla** antes de consulta; ≥10/12 proponen una pregunta discriminante y tras la respuesta interpretan bien una pareja nueva; 12/12 retiran la construcción y su hecho derivado con contraevidencia; 12/12 conservan hechos de fuente independiente; 12/12 reinicios y renombrados, y 12/12 incompatibles se abstienen. Control G-1 y solo memoria no aprenden la tercera superficie con dos ejemplos; ninguna respuesta inventada. Presupuesto completo 30 s CPU, 45 s pared, 128 MiB RSS, 128 hechos por predicado, 256 propuestas. Medir CPU por adquisición de raíces, recolección, selección, feedback, uso, retiro, persistencia e inferencia, además de ejemplos y propuestas. Repetir `PYTHONHASHSEED=0/1` solo si la primera corrida pasa. Si falla, detener, registrar el límite y no relajar puerta.

Un éxito demostraría aprendizaje encadenado de superficies y elección de evidencia en un mundo simple, **no** comprensión de documentos abiertos, anáfora, causalidad ni creación de semántica intensional.

## En palabras fáciles de entender

Leobot ya puede reconocer algunas relaciones después de leer varios ejemplos. Ahora queremos que use lo aprendido para entender una frase nueva que podría significar dos cosas, pregunte por un caso que las separe y espere la respuesta. No le daremos el nombre interno de las relaciones. Si corrige su interpretación, deberá borrar los datos que nacieron de ella sin tocar los demás.
