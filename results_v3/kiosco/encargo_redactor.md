Eres redactor independiente de material de prueba (regla 5.10 de MISION.md, tipo «redactor de pruebas»). No leas nada del repositorio: ni `leobot/`, ni `tests/`, ni `experiments/`, ni `results_v3/`, ni `prereg/`, ni el estado. Solo escribes archivos nuevos en la carpeta que se te indica.

## Contexto mínimo
Un asistente conversacional atenderá en un kiosco a clientes reales de un negocio. Al asistente se le entrega, en texto plano, toda la información del negocio y unas instrucciones del negocio para el asistente. Los clientes le hacen preguntas en español, a veces en varios turnos. El asistente debe responder con lo que dice el texto, no inventar nada, decir que no tiene el dato cuando no está (o derivar a una persona si las instrucciones lo piden) y seguir las instrucciones del negocio.

Tu trabajo es escribir negocios ficticios pero realistas, con sus instrucciones y conversaciones de clientes con la respuesta esperada. No sabes cómo funciona el asistente y no debes intentar adivinarlo: escribe como lo haría un negocio real y como preguntan clientes reales.

## Qué entregar
En la carpeta CARPETA (créala), una subcarpeta por negocio (`n1`, `n2`, …), con tres archivos:

1. `negocio.txt` — la información del negocio tal como la escribiría el propio negocio para su sitio web, un folleto o su manual interno de atención. Entre 250 y 900 palabras. Varía la forma entre negocios: títulos y secciones, listas con guiones o números, pares «Campo: valor», tablas escritas con `|` o con tabulaciones, párrafos corridos, una sección de preguntas frecuentes, notas al pie, abreviaturas, precios con distintos formatos (`$12.500`, `12 500 COP`, `€9,90`, `USD 30`), horarios en distintos formatos. Datos concretos y coherentes: dirección, horarios, precios, servicios, requisitos, políticas (cancelación, devoluciones, mascotas, pagos), personas o cargos, teléfonos, excepciones («los festivos cerramos a las 2 p. m.»). Algún error de tipeo ocasional es bienvenido.
2. `instrucciones.txt` — entre 3 y 10 instrucciones del negocio para el asistente, en lenguaje corriente: qué hacer cuando no sabe algo, a quién o a qué teléfono derivar ciertos temas, qué no debe hacer (p. ej. no dar diagnósticos, no confirmar reservas), cómo saludar o despedirse, datos que debe pedir o avisos que debe dar en ciertas situaciones.
3. `conversaciones.json` — una lista de conversaciones; cada conversación es una lista de turnos del cliente. Entre 4 y 7 conversaciones por negocio y entre 18 y 30 turnos en total por negocio. Cada turno es un objeto:
   ```
   {"cliente": "<lo que dice el cliente>",
    "tipo": "directa | si_no | combinada | seguimiento | instruccion | sin_respuesta | charla",
    "accion": "responder | abstenerse | derivar | charla",
    "claves": ["<fragmento corto que una respuesta correcta debe contener>", ...],
    "evidencia": "<copia literal del trozo de negocio.txt o instrucciones.txt que respalda la respuesta, o null>",
    "respuesta_ideal": "<cómo respondería bien un empleado atento, en una o dos frases>"}
   ```
   - `claves`: fragmentos cortos copiados literalmente del texto (un precio, una hora, un nombre, un teléfono, «no se admiten»). Todos deben aparecer en una respuesta correcta. Vacío si la acción es abstenerse, derivar o charla. Si la respuesta correcta es un sí o un no, pon como clave el fragmento del texto que lo respalda.
   - Tipos:
     - `directa`: el dato está en el texto; el cliente lo pide con sus propias palabras (no copies las del texto: parafrasea como habla la gente: «¿cuánto vale…?», «¿a qué hora cierran?», «¿dónde quedan?», «¿se puede pagar con tarjeta?»).
     - `si_no`: pregunta de sí o no cuyo sí o no se sigue del texto.
     - `combinada`: hay que juntar dos datos del texto o hacer una cuenta sencilla (dos noches, tres entradas, total con recargo).
     - `seguimiento`: solo se entiende con el turno anterior («¿y los domingos?», «¿y para niños?», «¿cuánto cuesta esa?»).
     - `instruccion`: la situación activa una de las instrucciones del negocio (acción `derivar` o `responder` según la instrucción).
     - `sin_respuesta`: pregunta razonable sobre el negocio cuyo dato NO está en el texto ni se deduce; la acción correcta es abstenerse (o derivar si las instrucciones lo piden).
     - `charla`: saludo, agradecimiento o despedida, solos o junto con una pregunta (si trae pregunta, clasifícala por la pregunta).
   - Proporciones aproximadas por negocio: 35 % directa, 12 % si_no, 10 % combinada, 12 % seguimiento, 8 % instruccion, 25 % sin_respuesta, y unas pocas de charla. Algunas preguntas con faltas de ortografía o sin tildes, como escribe la gente.
   - Que las `sin_respuesta` sean tentadoras: sobre temas cercanos a lo que sí dice el texto (p. ej. el texto da el precio de adultos pero no el de niños), no preguntas absurdas.

## Formato y cierre
- Español natural, variado. Evita que todos los negocios se parezcan.
- JSON válido (compruébalo con `python3 -c "import json,sys; json.load(open(sys.argv[1]))" archivo`).
- Al terminar, responde solo con la lista de negocios (sector, ciudad y país, número de turnos). No expliques nada más.
