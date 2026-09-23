# G-9 — gramática compositiva desde demostraciones formales

## Decisión y procedencia

G-7d falló aun con etiquetas débiles mayormente correctas; G-8 mostró que memorizar reformulaciones completas tampoco transfiere. [BabyDS (Ashrafzadeh, Hough y Eshghi, 2026)](https://www.mdpi.com/2226-471X/11/5/99) ofrece otra hipótesis: mantener hipótesis de acciones léxicas que, **compuestas**, produzcan el significado de una instrucción; actualizar sus probabilidades incrementalmente, en vez de elegir un vínculo aislado de palabra a etiqueta. Su semántica de entrenamiento es suministrada y su gramática computacional está diseñada. En G-9 el SQL oficial de educación será una **demostración explícita**, no una respuesta inferida desde texto crudo. Lo inducido será la correspondencia reutilizable texto→operadores. No se atribuirá a Leobot invención del SQL ni comprensión abierta.

## Fuente y separación

MultiSpider `train_es.json` y `tables_es.json` con revisión y hashes de G-6. Ocho bases del inventario actual, preguntas españolas revisadas tras traducción. Deduplicar SQL dentro de cada base antes de medir transferencia para que dos paráfrasis de una misma consulta no inflen capacidad. Dejar una base completa fuera de educación en cada vuelta; tres semillas 163/223/277 fijan orden y particiones. Programas SQL de las siete bases fuente se entregan al learner solo como demostraciones por una interfaz tipada; en la base excluida, SQL gold queda **solo en el evaluador**. `dev_es` y bases nuevas quedan cerrados hasta un ensayo congelado posterior. Ningún identificador de base, pregunta o respuesta se convierte en regla.

## Puerta 0: expresividad compartida, antes del learner

Normalizar cada SQL estructurado como una **firma de acciones** sin IDs de tablas/columnas ni valores: número de proyecciones y sus agregadores, presencia de unión, filtro, grupo, orden, límite, subconsulta y operaciones de conjuntos. Registrar aparte aridad y combinaciones, no contar miles de casos de una firma como capacidades distintas. Antes de programar un learner, exigir al menos 120 SQL distintos en las ocho bases, al menos 20 firmas con dos o más acciones presentes en al menos dos bases, y al menos 15 consultas por base excluida cuya firma aparezca entre las otras siete. Si falla, descartar esta fuente/representación para G-9; no reducir el umbral tras verla. Este paso es inventario del evaluador, no aprendizaje.

## Learner condicionado a puerta 0

Programa declarativo seguro: acciones tipadas y composición de operadores del AST ya representables por el motor; hipótesis para palabras y frases cortas; enumerar solo combinaciones que reproduzcan la firma de la demostración. Conservar rivales, actualizar pesos explícitos por apoyo/contraevidencia al estilo de un esquema incremental de hipótesis; no `eval`, red, SQL ejecutable del learner ni LLM. Reutilizar `Language` para construcciones y persistencia, retirando la búsqueda léxica duplicada de G-7d si funciona. El motor no recibe los ejemplos de comprobación ni importa evaluadores.

Tratamiento frente a `Language` actual con superficies exactas, bag de palabras G-7d, memoria exacta, fresco, mismas demostraciones sin composición y programas de enseñanza barajados. Renombrar completamente IDs y valores; invertir una pista auxiliar; incluir firma incompatible, contraevidencia que retire hipótesis y dependientes, guardar/cerrar/cargar. Evaluar firmas de programas **completas** en bases excluidas, no solo acciones presentes por separado, e informar coberturas por estructura. Tres órdenes y `PYTHONHASHSEED=0/1`.

## Puerta 1, costo y promoción

En cada orden, ≥60 % de firmas completas correctas sobre consultas estructuralmente elegibles de bases excluidas, ≥15 puntos porcentuales sobre el mejor control y éxito en al menos dos familias no isomorfas (por ejemplo unión+filtro frente a agregación+orden), sin respuestas seguras en incompatibles. Máximo 1 000 hipótesis por consulta, CPU ≤120 s, pared ≤180 s y RSS ≤256 MiB por orden; p95 de interpretación compilada ≤10 ms fuera de una KB grande. Medir lectura, adquisición, búsqueda, validación, consolidación, respuesta, ejemplos, candidatos y RAM. Si puerta 1 falla, conservar resultado y no integrar. Si pasa, congelar motor, crear reserva por hash con bases no usadas y comprobar latencia con 100 000 hechos y regressión completa antes de tag. Ni éxito en firmas ni demostraciones equivale a lectura de documentos reales, AGI o «solo falta información».
