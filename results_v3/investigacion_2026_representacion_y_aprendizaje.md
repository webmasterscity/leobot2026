# Investigación sobre representación y aprendizaje

Revisión del 27 de septiembre de 2026. No contiene una mejora demostrada de Leobot.

## En palabras fáciles de entender

Probamos separar dos preguntas internas: si corresponde contestar y qué frase
responde mejor. Eso dio una mejora parcial, pero no alcanzó las condiciones
fijadas. También probamos aprender combinaciones de las pistas disponibles;
cambiar ese modo de aprender no bastó. Antes de añadir otro aprendiz hay que
comprobar si recibe información capaz de distinguir las frases correctas.

Encontramos investigaciones recientes donde se aprenden reglas y relaciones
sin redes neuronales. Sus resultados merecen atención, pero algunos usan
equipos mucho mayores, problemas distintos o información de entrada que aquí
no tenemos. También hay colecciones de maneras distintas de decir algo; sus
agrupaciones pueden equivocarse. Ninguna de esas cifras garantiza el 60 % en
Leobot. El próximo control medirá cuánto podrían ayudar, incluso en el mejor
caso, las formas de datos que otra prueba ya aprendió de textos humanos.

## Fuentes que cambian la decisión

- [Graph Tsetlin Machine, versión 2 del 6 de mayo de 2026](https://arxiv.org/html/2507.14874v2):
  aprende conjuntos de condiciones conectados entre partes de una entrada. Es
  aprendizaje lógico, sin necesitar una red neuronal en el mecanismo propuesto.
  Pero sus pruebas, salvo una, usan una máquina con ocho H100, 112 núcleos y
  2 TB de RAM; no acreditan nuestro presupuesto de CPU. En seguimiento de acciones
  usa estados antes/después como nodos y acciones como conexiones, con una versión
  modificada de Tangram. Compara con cifras publicadas por otros autores, sin
  repetirlas. Sus 57,92 % con cinco instrucciones no son lectura libre de negocios.
  El ensayo usa 800 conjuntos de condiciones, 12 niveles y 50 recorridos de
  enseñanza. **Decisión:** estudiar la representación que preserva relaciones;
  no copiar el aprendiz ni presentar esos resultados como comprensión de prosa.
- [Zhang, Jiao y Granmo, ICLR 2026](https://proceedings.iclr.cc/paper_files/paper/2026/file/6c83f1f1290e80236587e4c89fa24f4e-Paper-Conference.pdf):
  analiza convergencia al aprender operaciones lógicas. Los teoremas para varios
  valores binarios suponen tiempo ilimitado y condiciones sobre la cantidad de
  patrones y parámetros. Etiquetas equivocadas impiden convergencia exacta;
  variables irrelevantes no necesariamente la impiden. No demuestra que el
  aprendiz descubra por sí mismo la representación del lenguaje o cumpla 5 ms.
  **Decisión:** no confundir capacidad de aprender una función, dada una entrada
  suficiente, con disponibilidad de esa información en nuestros 25 rasgos.
- [Repositorio Hierarchical Tsetlin Machine, consultado en septiembre de 2026](https://github.com/cair/HierarchicalTsetlinMachine):
  propone jerarquías de condiciones y un ejemplo de paridad con ruido. El artículo
  figura todavía como pendiente; aplicaciones al lenguaje y reutilización de
  partes aparecen como trabajo futuro. **Decisión:** no tratar una propuesta de
  investigación como una capacidad disponible y comprobada para este proyecto.
- [TaPaCo, LREC 2020](https://aclanthology.org/2020.lrec-1.848.pdf):
  32 691 grupos y 85 064 frases españolas escritas en Tatoeba, agrupadas mediante
  conexiones de traducción. Los grupos se crean automáticamente y pueden perder
  distinciones importantes; la revisión manual presentada cubre inglés, alemán
  y francés, no español. Muchas frases son ejemplos breves construidos y pueden
  venir de hablantes no nativos. **Decisión:** no enseñar equivalencia universal
  desde esos grupos. G-8 y F-13 ya fallaron al aprender sustituciones locales o
  varias redacciones; una fuente mayor por sí sola no refuta esos fallos.
- [Spanish Paraphrase Corpora, GIL-UNAM](https://huggingface.co/datasets/GIL-UNAM/SpanishParaphraseCorpora):
  reformulaciones humanas alrededor de un artículo sobre sushi, con textos que
  comparten vocabulario pero cambian de tema. **Decisión:** su contraste es útil
  conceptualmente, pero ese único origen no basta para enseñar correspondencias
  generales entre preguntas de clientes y respuestas de cualquier negocio.

## Próxima comprobación acotada

PAR-1 ya aprendió asociaciones hacia formas de cifras y signos, pero su uso
aislado no mejoró las respuestas útiles. G-82 medirá su alcance máximo favorable
antes de intentar combinarlas con el selector. No cambia la confianza, enseña
tablas nuevas ni abre una reserva. Si ni ese límite permite un aporte suficiente,
se abandona esta combinación de formas sin consumir otro ajuste completo.
