# G-28b — hueco exigido, tramo sin palabras de la pregunta y correspondencias léxicas aprendidas

Fecha: 2026-09-23. Preregistro previo al código. Base: motor de `freeze-G-28` (`aaea9a1a`), cuya puerta falló (reserva F1 0,218 < 0,25; [resultado](../results_v3/g28_reading_alignment_2867501594_hashseed0.json)). Último estable: `estable-G-2`.

## Fallos medidos y causas

1. **Respuestas inventadas a preguntas sin hueco.** En la sonda, preguntas de sí/no («¿Puede Leobot depender de redes neuronales?») recibieron un tramo. Causa: sin palabra de la pregunta ausente de la oración, la clave cae en `*` y el modelo elige igual un tramo.
2. **Tramos que repiten la pregunta.** «¿Qué manda sobre la ambición?» → «ambición». El rasgo `question_inside` cuenta todas las palabras, incluidas las de poco peso, y no alcanza a castigar.
3. **Paráfrasis.** La pregunta y el texto usan palabras distintas para lo mismo; el pasaje correcto quedó primero solo en 72–78 % de los casos en desarrollo y la oración en 77 %.

## Hipótesis (mecanismos aprendidos, sin listas de palabras)

(a) Solo hay respuesta por tramo si la pregunta contiene una palabra ausente de la oración cuya fuerza aprendida como marcador de hueco es alta: fue clave en ≥5 ejemplos de educación y estuvo ausente de la oración que responde en ≥50 % de las preguntas donde apareció. Si no, abstención `no_gap_marker`.
(b) Se mide en la educación con qué frecuencia la respuesta correcta contiene una palabra de anclaje de la pregunta (palabras de la pregunta presentes en la oración con peso ≥ la media de la oración). Si esa frecuencia es <5 %, los tramos con anclajes se descartan; si no, quedan como rasgo.
(c) Correspondencias léxicas entre palabras de pregunta y de oración respondiente, aprendidas de los ejemplos con el modelo de alineación IBM-1 (EM, 5 iteraciones; [Brown y otros, 1993](https://aclanthology.org/J93-2003.pdf)), podadas a probabilidad ≥0,2 con apoyo ≥3. Una palabra de la pregunta sin coincidencia literal cuenta como presente si la oración tiene una palabra correspondiente, con peso reducido por su probabilidad, para pasaje, oración y vecinos del hueco.
Alternativa: (a)–(b) solo bajan cobertura sin subir F1; (c) no aprende correspondencias útiles con 2000 ejemplos o introduce ruido.

## Datos, controles y puerta

Iguales a G-28 (educación 2000 de `test` semilla 2828; reserva 200 de `dev` sin los 20 del tablero, semilla de `freeze-G-28b:leobot`), con estos cambios: el **desarrollo visible** usa 300 ejemplos de `test` cuyo párrafo no está en la educación; se añade el control **sin hueco**: para cada caso de reserva, la oración que contiene la respuesta, convertida en pregunta tal cual («¿<oración>?»), debe recibir abstención; y la **ablación de correspondencias** (mismo motor, correspondencias desactivadas).

Puerta (hashseed 0 y 1, salidas idénticas): F1 ≥ 0,25 y exactas ≥ 0,10; ventaja ≥ 0,05 sobre la ablación de G-28 y ≥ 0,10 sobre educación barajada; fresco 0 respuestas; honestidad ≥ 90 %; **sin hueco ≥ 95 % de abstenciones**; renombrado a ≤ 0,03; reinicio idéntico; memoria conjunta ≥ 0,8 × tratamiento; latencia p95 ≤ 10 ms y ≤ 200 ms; educación ≤ 60 s CPU; RSS ≤ 256 MiB. La ablación de correspondencias se informa (no es puerta): si no ayuda, (c) se retira antes de cualquier tag. Si la puerta falla, se registra sin relajarla.

## En palabras fáciles de entender

Leobot a veces contestaba con un pedazo de texto preguntas que se responden con sí o no, o repetía palabras de la pregunta. Ahora, si no hay un hueco claro que llenar, dirá que no sabe. Y aprenderá, de los ejemplos resueltos, qué palabras suelen significar lo mismo en la pregunta y en el texto, para encontrar mejor dónde está la respuesta.
