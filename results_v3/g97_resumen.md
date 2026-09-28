# G-97 — resultados de las tres alternativas

2026-09-27. Tanda cerrada por instrucción del usuario. Sin nueva versión estable.

## En palabras fáciles de entender

Probamos tres ayudas para cuando Leobot dice «No lo sé»: reglas escritas a
mano, un modelo de lenguaje ya entrenado y un modelo pequeño entrenado aquí.
Ninguna demostró cumplir juntas las tres metas: contestar bien al menos seis
de cada diez preguntas que tienen respuesta, evitar errores y responder en
menos de cinco milisegundos.

Las reglas fueron la única ayuda que aumentó las respuestas útiles en la
comparación común: de 29 a 36 entre 102 preguntas con respuesta. También
resolvieron tu ejemplo completo de la panadería: citaron el horario y la
dirección, conservaron la respuesta sobre cheques y dijeron que no sabían
si había estacionamiento. Lo hicieron rápidamente. Esto funciona en el
prototipo experimental; el Leobot estable que cargas sigue igual.

El modelo de lenguaje probado tardó aproximadamente entre 1,6 y 1,9 segundos
cuando intervino en la panadería. Para la dirección escogió un texto sobre
tortas. Copiar una frase verdadera no basta para contestar bien una pregunta.
El modelo que entrenamos aprendió algunas relaciones entre preguntas y
respuestas, pero todavía no elige con suficiente acierto los fragmentos de
los negocios. Su control de confianza impidió añadir respuestas.

La comprobación con negocios nuevos quedó incompleta. Hubo un primer examen
mal redactado, un segundo intento que agotó el tiempo y cuatro documentos
del último intento que incumplieron la cantidad de preguntas pedida. Se
conservan esos fallos y sus costos; no los contamos como resultados de Leobot.

Mi propuesta, si decides retomar después, es enseñar a elegir el fragmento
exacto que contesta cada pregunta y reconocer cuándo falta el dato. También
habría que revisar las respuestas equivocadas que Leobot ya entrega: una
ayuda que solo actúa cuando calla no puede corregirlas. Por ahora paramos.

## Comparación común terminada

Seis negocios y 157 turnos ya usados en desarrollo: 102 preguntas con dato,
47 sin dato y ocho de otras clases. Cifras del evaluador automático existente
por coincidencia de claves. **No son un examen independiente nuevo ni se
comparan directamente con el 35,9 % histórico de otro banco y otro juez.**

| Variante | Útiles entre 102 con dato | Errores nuevos detectados | Tiempo del 95 % / máximo, ms |
|---|---:|---:|---:|
| Leobot estable | 29 (28,4 %) | Referencia | 0,235 / 0,583 |
| Con reglas manuales | 36 (35,3 %) | 0 | 0,827 / 1,164 |
| Con modelo propio entrenado | 29 (28,4 %) | 0; no añade respuestas | 0,392 / 0,516 |
| Con modelo sin entrenar | 29 (28,4 %) | 0; no añade respuestas | 0,393 / 0,539 |
| Con modelo entrenado con parejas confundidas | 29 (28,4 %) | 0; no añade respuestas | 0,381 / 0,502 |
| Con LFM2.5-350M | Comparación extensa interrumpida | Sin cifra general completa | Véase panadería |

Las cinco variantes rápidas conservan 12 citas incorrectas ante preguntas
con dato y siete citas ante preguntas sin dato, según ese evaluador. Cero
errores nuevos no significa cero errores totales. Ninguna cita nueva contiene
texto ajeno a su unidad de origen; eso tampoco certifica pertinencia.

Cuando realmente se llama a la ayuda, el tiempo del 95 % / máximo fue
0,889 / 1,163 ms para reglas y 0,410 / 0,515 ms para el modelo propio.
Los tiempos incluyen la respuesta original y la ayuda, con documento y
modelos cargados, en CPU i7-13620H y una hebra de ejecución. Carga y preparación
se pagan aparte. Fuente: [medición común](g97_common_fast.json).

## Tu panadería, con el texto y la base exactos

| Pregunta | Estable | Reglas experimentales | LFM2.5-350M |
|---|---|---|---|
| ¿A qué hora abren? | No lo sé | Cita el horario 7:00–19:00, lunes a sábado | No lo sé |
| ¿Aceptan cheques? | Cita «No aceptamos cheques» | Igual | Igual |
| ¿Tienen estacionamiento? | No lo sé | No lo sé | No lo sé |
| ¿Dónde quedan?, sin historial | No lo sé | Cita Calle Real 12, frente a la plaza | Cita equivocada sobre tortas por encargo |

Reglas: tres respuestas útiles de tres posibles y abstención correcta en la
pregunta sin dato; máximo 0,346 ms. LLM —modelo de lenguaje—: una de tres,
una cita equivocada; mediana 1625,5 ms y máximo 1871,6 ms cuando interviene.
Su carga adicional tardó 196,2 ms. El modelo propio y sus controles conservan
las respuestas del estable. [Salidas completas](g97_user_diagnostic.json).

Se comprobó el formato de entrada contra la plantilla incluida en el archivo
del LLM, sin modificar las instrucciones tras ver sus respuestas. Un proceso
nuevo con otro orden de hashes reprodujo exactamente las seis variantes:
[comprobación de formato](g97_llm_template_check.json), [reinicio](g97_restart.json).

## Qué aprendió el modelo propio

Es una red que elige fragmentos, **no un LLM generativo**. Tiene 1 288 384
parámetros y se entrenó desde cero con 6000 parejas humanas de preguntas y
respuestas de 703 sitios. En 1000 preguntas de otros 136 sitios acertó 581
elecciones entre 16 opciones; el control sin entrenar acertó 70 y el de
parejas confundidas 397. Es aprendizaje de esa tarea, no utilidad del kiosco.

En las 61 preguntas contestables que el estable dejaba sin responder, eligió
bien el fragmento en seis; los controles en una. Sin el control de confianza
también propondría una cita en las 40 preguntas sin dato que el estable dejaba
sin responder. La confianza máxima aprendida fue 0,3469, menor que el mínimo
fijado antes de medir, 0,4. Por eso no añadió respuestas. Se conservó ese
mínimo. [Enseñanza](g97_training.json), [elecciones antes del filtro](g97_common_raw_proposals.json).

## Comprobación independiente incompleta

1. Primera redacción: el campo ambiguo `cliente` recibió nombres de personas,
   no preguntas. Otro juez marcó los 96 casos como problemas del examen.
   Sus cifras de utilidad son inválidas: [diagnóstico](g97_reserve_invalid.json),
   [juicio independiente](g97_judgment.json).
2. Segunda redacción con `question` explícito: agotó 600 segundos sin entregar
   material utilizable. [Registro](g97_author_v2_timeout.json).
3. Última redacción, ocho encargos pequeños: cuatro cumplieron las comprobaciones
   de formato; los otros cuatro produjeron nueve preguntas con dato y tres sin
   dato, frente a las ocho/cuatro fijadas. No se evaluó una selección reducida
   ni se cambiaron etiquetas para hacerla pasar. Las ocho entregas se conservan
   en `g97_author_part1.json` a `g97_author_part8.json`.

La comparación amplia del LLM se detuvo después de observar 459,89 segundos
de CPU porque ya incumplía ampliamente el tiempo exigido. No hay una cifra
completa de su utilidad general. **El protocolo completo G-97 no se terminó;
esta tanda se cierra sin validación nueva de generalización ni promoción.**

## Costo y comprobaciones

- Adquisición y compilación principal: 137,505 segundos de CPU; enseñanza,
  controles y confianza: 26,546; comparación rápida: 3,090; evaluación del
  examen inválido: 2,403; panadería y repetición: 14,626; examen de elecciones
  sin filtro: 2,278. El intento extenso detenido y las pruebas también cuentan.
- Suma local instrumentada: **al menos 654,892 segundos de CPU**. Faltan algunas
  mediciones, incluida la compilación del pequeño programa de enlace. Los
  costos anteriores de la base y del conjunto educativo fueron reutilizados.
  No se certifica el presupuesto total como si se hubiera medido completo.
- Memoria máxima registrada durante enseñanza: 1 140 960 KiB, unos 1,09 GiB.
  Las preparaciones por variante están separadas en los archivos de resultados;
  la carga inicial de `Bot.load` no se cronometró por separado.
- Trabajo externo: primera redacción 460,266 s, juez 82,525 s, segundo intento
  limitado a 600 s; ocho encargos finales suman 131,503 s individuales con dos
  simultáneos. Esta suma no es tiempo transcurrido global. Precio de lista
  informado conocido: **1,4596444 USD**, más el intento agotado de costo
  desconocido; no equivale a una factura comprobada. CPU remota desconocida.
- Tres comprobaciones específicas y trece rápidas pasan. Reinicio exacto en
  las seis variantes. Motor, base y código de respuesta experimental mantienen
  sus huellas registradas. Sin regresión completa nueva ni nueva versión estable.

Desglose y límites: [registro de cierre](g97_closure.json).

## Los dos modelos que sugeriste

[Laya](https://huggingface.co/convaiinnovations/laya) puede elegir entre opciones.
Su autor informa 193–464 ms en CPU y 32,8 ms en una GPU T4; no son mediciones
en este equipo. La cifra inferior a 0,5 ms corresponde a detección del idioma,
no a toda la respuesta. No se descargó ni se probó localmente en esta tanda.

[Span-01 Lite](https://openrouter.ai/respan/span-01-lite) puntúa comportamientos
como presentes, ausentes o no observables, según la
[documentación de sus autores](https://www.respan.ai/docs/documentation/span-01/concept).
No se hizo ninguna llamada de inferencia. Su descripción no demuestra que
resuelva preguntas documentales en menos de cinco milisegundos.

## Propuesta para una eventual continuación

Conservar el estable. Si el usuario decide retomar, priorizar enseñanza con
pregunta, documento, fragmento correcto y casos sin dato; medir por separado
si se elige bien y si se sabe cuándo callar. Incluir revisión de las respuestas
que el estable ya da: en esta muestra hay 12 incorrectas entre las 102 con
dato que las ayudas no pueden cambiar. El techo de este diseño, según el
evaluador automático, sería 90/102, incluso arreglando todas sus abstenciones.

Las reglas quedan como referencia experimental de una mejora pequeña. No
aportan autoaprendizaje ni prueba de generalidad. Los resultados no permiten
asegurar que alcanzaremos 60 % con las otras restricciones. **No se inicia
ninguna de estas propuestas: el usuario pidió terminar esta tanda y parar.**
