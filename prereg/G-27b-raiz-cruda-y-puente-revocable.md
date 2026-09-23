# G-27b — conservar la raíz cruda y unirla al significado elegido con un puente revocable

Fecha: 2026-09-23. Preregistro previo al cambio. Base estable `estable-G-1:leobot` = `0c5f3152b3c93273c25d4108e7b73bba0629d804`; base de trabajo `freeze-G-27:leobot` = `7dc3a3e9` (resultados en `results_v3/g27_raw_root_probe_2109973481_hashseed{0,1}.json`).

## Fallo, hipótesis y alternativa

G-27 superó su puerta pero midió una pérdida: con significados rivales abiertos, la frase se desvía a la recolección segura antes de la inducción cruda, y una tercera frase de la misma superficie sobre las mismas parejas ya no crea la raíz opaca de G-1 ni guarda sus hechos (0/12 frente a 12/12 de G-1 en la misma reserva). En desarrollo (semilla visible 27, 4 familias) se probó la reparación ingenua —registrar además la frase como evidencia cruda—: la raíz vuelve a nacer con la tercera frase y la versión espacial conserva sus dos hipótesis; pero al responder la pregunta, el motor actual enseña una construcción anclada sobre la misma superficie y la frase nueva pasa a `ambiguous` en 4/4. Ese es el choque que hay que evitar.

Hipótesis: (a) una afirmación que abre significados rivales sigue alimentando la inducción cruda, de modo que con tres frases se recupera la raíz de G-1 y se guardan sus hechos; (b) si al llegar la respuesta todas las observaciones del grupo ya se interpretan por una sola raíz cruda R, la respuesta no enseña construcciones: agrega dos reglas aprendidas que equiparan R con la relación elegida, con el orden de papeles derivado de las propias observaciones, y las registra en el grupo; (c) una respuesta contradictoria retira exactamente esas reglas y conserva los hechos de R, que son lo que dijo el texto. Sin raíz cruda el comportamiento de G-27 no cambia. Alternativa: el puente crea ciclos costosos, ambigüedad, pérdida de hechos independientes o retiro incompleto; entonces no integrar y registrar el límite.

Por qué equivalencia y no una sola dirección: en todas las parejas conocidas las dos extensiones coinciden en ambos sentidos (tres observaciones y la respuesta), y la construcción anclada de G-27 ya significaba «la superficie dice lo mismo que la relación» tanto al afirmar como al preguntar. Las reglas son de origen `learned`, así que el probador responde `hypothesis` y no `supported`. No se agrega el puente si un hecho conocido de un lado tiene negado explícitamente su imagen en el otro. Si unas observaciones se interpretan por R y otras no, o por raíces u órdenes distintos, la respuesta termina en conflicto y no promueve nada.

No se agrega learner, lista de verbos ni fuente nueva: se reutilizan antiunificación cruda, versión espacial, MetaController, reglas aprendidas con registro de su identificador (como las reglas condicionales V5.6) y el retiro de G-26b. Es la reparación de una regresión con mecanismos existentes; ninguna lectura nueva cambió esta decisión.

## Experiencia, controles y reserva

Mismo generador que G-27 —vocabulario y entidades nuevos, relación verdadera alterna y orden de papeles invertido en la mitad— pero con **tres** frases de la tercera superficie (parejas 0–2) antes de preguntar. Todo llega por `Bot.respond` en texto natural; el entorno responde sí/no solo después de la propuesta; el evaluador solo lee el estado y usa `answer_atom` para puntuar.

Evaluación: 12 familias y 12 renombradas; semilla de los primeros ocho dígitos de `git rev-parse <commit>:leobot`, generada tras congelar motor y evaluador. Controles: motor `estable-G-1` y motor `freeze-G-27` extraídos del repositorio y ejecutados en procesos hijos con la misma secuencia; bot fresco; solo memoria (`grounded_language=False`); incompatibles sin negación y con una sola hipótesis; renombrado total; ablación del registro del puente (misma historia, respuesta contradictoria, el puente debe quedar); guardar/cargar antes de la respuesta, tras el uso y tras el retiro.

Puerta:

- **12/12** familias recuperan la raíz: la tercera frase devuelve `raw_relation_learned` con una raíz distinta de las dos de educación y guarda los tres hechos; el grupo mantiene dos hipótesis sin promover y no existe puente antes de la respuesta. Nunca menos que G-1 en la misma reserva.
- **≥10/12** proponen la pregunta discriminante y, tras la respuesta, promueven por puente sin enseñar construcciones; la frase de una pareja nueva sigue interpretándose sin ambigüedad por la raíz cruda, la relación elegida queda deducida como `hypothesis` para esa pareja con el orden de papeles correcto, la otra relación queda `unknown`, y la dirección inversa (un hecho dicho con la relación elegida) se deduce para la raíz cruda.
- **12/12** retiran con contraevidencia: `grounding_conflict`, las dos reglas desaparecen y ambas deducciones vuelven a `unknown`.
- **12/12** conservan los hechos de la raíz cruda (parejas 0–2 y la nueva), los de educación y el hecho dicho con la relación elegida, y la frase sigue interpretándose por la raíz.
- **12/12** reinicios (pregunta pendiente, puente y retiro sobreviven a guardar/cargar), 12/12 renombrados, 12/12 incompatibles, solo memoria, G-1 y fresco sin puente ni deducción; 24/24 sin respuestas inventadas; 12/12 la ablación conserva la deducción.
- El evaluador de G-27, sin cambios, supera su propia puerta con el motor congelado de G-27b y su propia semilla de árbol.
- Presupuesto completo 30 s CPU con hijos, 45 s pared, 128 MiB RSS, 256 propuestas. Medir CPU por raíces, recolección, selección, respuesta, uso, retiro, persistencia e inferencia. Repetir `PYTHONHASHSEED=0/1` solo si la primera corrida pasa. Si falla, detener, registrar el límite y no relajar la puerta.

Un éxito demostraría que el aprendizaje desde texto crudo y la elección por pregunta conviven sin perder capacidades en un mundo simple, **no** comprensión de documentos abiertos ni descubrir un significado fuera de las hipótesis. Límites conocidos y no probados aquí: otro aprendiz que retire reglas aprendidas de la relación elegida también retiraría el puente, y la versión espacial sigue siendo de mundo cerrado.

## En palabras fáciles de entender

En la prueba anterior, Leobot aprendió a preguntar cuando una frase nueva podía significar dos cosas. Pero, mientras esperaba la respuesta, dejó de aprender esa frase como antes: una tercera frase ya no quedaba guardada. Ahora queremos que haga las dos cosas. Que siga guardando lo que dicen las frases, y que, cuando le respondan, una ese aprendizaje con el significado correcto mediante dos reglas que se pueden deshacer. Si después le dicen que se equivocó, quitará solo esas dos reglas y conservará lo que las frases decían.
