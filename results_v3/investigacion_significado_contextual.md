# Aprender significado condicionado por la pregunta completa

Revisión del 2026-09-27, durante G-75. No es evidencia de una mejora de Leobot.

## En palabras fáciles de entender

Leobot ha probado aprender parejas de palabras, formas de datos y relaciones
entre participantes. Falta comprobar si puede descubrir por sí mismo grupos de
preguntas y de respuestas que suelen ir juntos. La pregunta completa ayudaría
a decidir qué grupo interesa, y ese grupo orientaría la búsqueda en el texto
del negocio. Los grupos tendrían que salir de ejemplos escritos por personas,
sin nombres ni significados asignados por el desarrollador. Si solo reconoce
el tema y confunde los datos, la prueba debe descartarlo.

## Fuentes y decisión

- [Poon y Domingos, EMNLP 2009](https://aclanthology.org/D09-1001.pdf): agrupan
  fragmentos sintácticos y sus participantes de forma recursiva. En GENIA
  reportan 295 respuestas correctas de 334 emitidas, sobre preguntas generadas;
  eso no equivale a cubrir el 88 % de las preguntas abiertas. Su agrupación
  confunde antónimos y añade una penalización manual basada en conjunciones.
  No se traslada esa regla a Leobot. El trabajo respalda examinar participantes,
  pero no prueba el rendimiento de G-75 ni la rapidez requerida.
- [Titov y Klementiev, ACL 2011](https://aclanthology.org/P11-1145.pdf): modelo
  de grupos y papeles por probabilidad; unas 300 000 iteraciones de muestreo.
  Reportan 259/325 respuestas correctas en el mismo entorno biomédico. Grupos
  demasiado amplios explican gran parte de los errores; menos de 80 preguntas
  distintas reciben respuesta en cualquiera de los modelos comparados.
  Decisión: no añadir un agrupador de relaciones que trate similitud como
  equivalencia. Costos de respuesta inferiores a 5 ms no establecidos.
- [Zolaktaf y colaboradores, taller de 2011](https://people.cs.umass.edu/~wallach/workshops/nips2011css/papers/Zolaktaf.pdf):
  relacionan grupos aprendidos de preguntas con grupos distintos de respuestas.
  Usan 15 822 pares de Stack Overflow y preguntas duplicadas identificadas por
  usuarios. El método supera LDA; su medida Top1 queda entre 0,108 y 0,131,
  y no se compara con el lector de Leobot. Decisión: el mecanismo merece una
  prueba pequeña como pista adicional, no como demostración de comprensión.
- [Mimno y colaboradores, EMNLP 2009](https://aclanthology.org/D09-1092.pdf):
  aprenden grupos compartidos entre documentos vinculados en distintas lenguas,
  con vocabularios separados. No requieren traducciones palabra por palabra.
  Aplicar dos vocabularios a preguntas y respuestas sería una adaptación propia,
  no una reproducción de su resultado multilingüe.

La búsqueda incluyó publicaciones de 2026. Los mecanismos compatibles y límites
de CoNLL, Poker y Reducer ya están en
[la investigación anterior](investigacion_2026_g71.md). Los artículos recientes
de integración neuronal no autorizan introducir redes en el motor. Se incluyen
aquí trabajos antiguos porque describen mecanismos concretos aún pertinentes.

## Diferencia que tendría que demostrarse

G-65/G-70 condicionan asociaciones a palabras o parejas; G-75 verifica relaciones
y participantes, con alcance limitado por Predicate Matrix. PAR-1 agrupa palabras;
PAR-3, en la otra carpeta, consulta ejemplos humanos parecidos. Una alternativa
basada en grupos de preguntas completas tendría que transferir sin conservar
los ejemplos y superar un control con parejas pregunta/respuesta desordenadas.
La adaptación acotada quedó después preregistrada como [G-76](../prereg/G-76-grupos-de-preguntas-y-respuestas.md).
