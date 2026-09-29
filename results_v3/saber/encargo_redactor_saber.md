# Encargo para redactores de preguntas de conocimiento general cotidiano

Eres redactor independiente de material de prueba (regla 5.10 de `MISION.md`). Tu único trabajo es escribir un archivo de preguntas.
No leas ninguna otra carpeta del repositorio (en particular, no leas `leobot/`, `tests/`, `experiments/`, `prereg/` ni `results_v3/`
salvo este archivo). No ejecutes código del proyecto.

## Qué escribir
Preguntas en español que una persona adulta corriente sabría contestar sobre el mundo y la vida cotidiana, con su respuesta breve y
correcta. Escríbelas como las haría cualquier persona, variadas en tema y en forma (preguntas abiertas, de sí o no, de elegir, de
contar, de comparar…). Sin preguntas capciosas, sin cultura especializada, sin temas de actualidad ni fechas recientes.

Además, alrededor de un 15 % de preguntas que **no** se pueden contestar con conocimiento general porque dependen de datos
particulares (de una persona, de un lugar concreto, de un momento concreto); su respuesta esperada es que no se puede saber.

## Formato
Un solo archivo JSON en la ruta que te indiquen, con esta forma:

```json
[
  {"id": "R1-001", "pregunta": "…", "respuesta": "…", "aceptables": ["…"], "tipo": "contestable"},
  {"id": "R1-002", "pregunta": "…", "respuesta": "no se puede saber", "aceptables": [], "tipo": "sin_respuesta"}
]
```
- `respuesta`: la respuesta más natural y breve; `aceptables`: otras formas igualmente correctas (sinónimos, cifras escritas de
  otro modo); puede ir vacío.
- Cada pregunta, independiente de las demás (sin «y eso», «lo anterior»…).
- Cantidad: la que te indiquen.

Entrega un informe final de una línea con cuántas preguntas escribiste de cada tipo.
