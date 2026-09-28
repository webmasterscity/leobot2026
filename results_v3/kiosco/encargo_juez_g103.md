Eres verificador independiente (regla 5.10 de MISION.md), tipo **juez ciego**. No leas nada del repositorio; trabaja solo con la carpeta que se te indica.

## Contexto mínimo
Un asistente atiende clientes en un kiosco con el texto de un negocio y unas instrucciones del negocio. Contesta citando el texto o las instrucciones, o dice que no sabe. No sabes qué sistema produjo cada respuesta ni cómo funciona ninguno: califica solo lo que ves.

## Qué recibes
En tu carpeta:
- `items.json`: una lista de ítems. Cada uno tiene `id`, `negocio` (subcarpeta), `turnos_previos_del_cliente`, `cliente` (lo que dijo el cliente), `tipo`, `accion_esperada`, `claves`, `evidencia`, `respuesta_ideal` (cómo respondería bien un empleado) y `respuesta_a_calificar`.
- Una subcarpeta por negocio con `negocio.txt`, `instrucciones.txt` y `conversaciones.json`. Lee `negocio.txt` e `instrucciones.txt` del negocio de cada ítem para comprobar lo que dice la respuesta.

## Qué entregas
Un archivo `veredictos.json` en tu carpeta: una lista de objetos `{"id": "<id del ítem>", "veredicto": "<etiqueta>", "nota": "<una frase>"}`, uno por ítem, sin omitir ninguno. Comprueba que es JSON válido (`python3 -c "import json,sys; json.load(open(sys.argv[1]))" veredictos.json`). Responde solo con «listo» y el número de ítems.

## Etiquetas
La respuesta es de una de estas formas; usa el juego de etiquetas que corresponde.

**A. Cita del texto** (empieza con «No lo tengo seguro. Lo más cercano que dice el texto es: «…»») o **respuesta plana** (solo el fragmento):
- `util`: lo citado responde lo que el cliente preguntó o su parte principal, y un cliente que lo lea recibe un dato correcto.
- `honesta`: lo citado no responde lo pedido, pero el aviso deja claro que no es el dato y nada engaña.
- `enganosa`: aun con el aviso, llevaría al cliente a creer algo falso o distinto de lo que preguntó (otro precio, otra fecha, otro servicio).
- Si es una respuesta plana (sin aviso): `correcta`, `incompleta`, `equivocada` o `inventada` (dice algo que no está en el texto).

**B. Cita de las instrucciones** (empieza con «Sobre eso, las indicaciones del negocio dicen: «…»»), en cualquier tipo de turno:
- `util`: la instrucción citada es la que aplica a lo que el cliente pidió y lleva al cliente por la salida correcta (contacto, persona, pasos, o le dice que eso no se hace aquí), o responde lo preguntado.
- `honesta`: la instrucción citada no es la que aplica pero no confunde ni contradice nada.
- `enganosa`: la instrucción citada llevaría al cliente a un contacto o acción equivocados para lo que pidió, o contradice lo que debe hacerse.

**C. «No lo sé…»** (con o sin instrucciones añadidas): si `accion_esperada` es `abstenerse`: `abstencion_correcta`; si es `derivar` y la respuesta no da la salida que pide la instrucción: `honesta`; si es `responder` y el dato estaba en el texto: `abstencion_indebida`.

Reglas generales:
- Juzga por lo que entiende un cliente, no por coincidencia de palabras. `claves` y `evidencia` son la ayuda del redactor del negocio, no un examen literal.
- No premies una cita larga por contener la respuesta escondida entre datos que no vienen al caso si el cliente no puede saber cuál es; tampoco castigues una cita completa que sí la contiene con claridad.
- Si un ítem es dudoso, elige la etiqueta más estricta que puedas justificar y anótalo en `nota`.
- No modifiques ningún archivo salvo `veredictos.json`.
