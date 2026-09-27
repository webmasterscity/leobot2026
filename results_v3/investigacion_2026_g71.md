# Investigación para aprender relaciones completas

Fecha de consulta: 2026-09-27. Decisión antes de G-71. Fuentes primarias,
versiones completas y comparación con los intentos conservados en el repositorio.

## En palabras fáciles de entender

Leobot encuentra a menudo el párrafo correcto, pero no entiende suficientemente
bien qué relación tiene con lo preguntado. Cambiar el puntaje de palabras o el
nivel de confianza ya produjo seis intentos sin una mejora suficiente.

Busqué investigaciones recientes que permitieran intentar algo distinto.
La primera enseña a reconocer juntos los participantes de una acción. Puede
ayudar a separar quién da algo, qué entrega y quién lo recibe. La segunda hace
que un programa proponga ejemplos y descarte explicaciones incompatibles con
lo aprendido. La tercera evita perder tiempo buscando reglas redundantes.

Ninguna publicación demuestra que Leobot vaya a alcanzar la meta. Algunas
necesitan ayuda que aquí está prohibida; otras resuelven problemas mucho más
limitados. Por eso se probará primero una pequeña adaptación de la primera,
con los mismos textos y medidas que una referencia existente. Las otras dos
quedan como posibilidades condicionadas, con sus límites documentados.

Si la adaptación no mejora, se descarta. Si mejora con frases ya analizadas,
todavía deberá hacerlo con texto corriente y luego con negocios nuevos. La
respuesta de la panadería sigue siendo una comprobación visible, nunca una
respuesta que se le enseñe para aparentar aprendizaje general.

## Publicaciones examinadas

### 1. Construcciones conjuntas — prioridad para una prueba

Van Eecke y Beuls, **CoNLL 2026**, julio, páginas 213–226:
[artículo y PDF oficiales](https://aclanthology.org/2026.conll-main.13/).
Aprende piezas para identificar acciones, asignar participantes conjuntamente
y elegir sentidos; una red de categorías conecta esas piezas. En inglés,
153 391 frases de entrenamiento y 1 000 de prueba aleatorias: F1 76,25 con
sentido exacto y 79,96 sin distinguir sentidos del mismo verbo. No son resultados
de preguntas sobre negocios. Usa análisis neuronal spaCy–BeNePar y anotaciones
PropBank; trabaja con participantes centrales, excluyendo modificadores como
el tiempo. No encontré una medición que avale cinco milisegundos. El tutorial
de código `fcg-net.org/fcg-propbank/` no respondió al acceso; el método sí pudo
revisarse en el artículo completo.

**Inferencia para Leobot:** aislar la restricción conjunta y reutilizar sus
probabilidades actuales. G-24 decide cada papel por separado; G-33 no aprende
estas combinaciones. F-12 ya factorizaba gramáticas: esa factorización sola no
se presenta como novedad. G-71 no copia el analizador neuronal ni presume que
la parte simbólica conservará las cifras del artículo.

### 2. Poker — posible invención de reglas, con límites pendientes

Patsantzis, **AAAI 2026**; versión ampliada del 4 de marzo:
[artículo completo v2](https://arxiv.org/html/2507.16405v2),
[publicación](https://ojs.aaai.org/index.php/AAAI/article/view/39010),
[código oficial](https://github.com/stassa/aaai_26_experiments/).
Genera ejemplos y elimina hipótesis mientras conserva la explicación de los
positivos conocidos. Compara con Louise en lenguajes formales, con 100 muestras
aleatorias. Más ejemplos generados reducen la generalización excesiva. Las formas
de reglas SONF fueron elaboradas manualmente; una regla adicional se usa solo
para palíndromos. La autora declara límites empíricos y de eficiencia pendientes.
Sus etiquetas generadas no son comprobaciones externas de hechos del mundo.

**Inferencia para Leobot:** estudiar una futura búsqueda de hipótesis recursivas
y ejemplos discriminantes. La novedad potencial sería ese espacio de hipótesis,
no decir «autocorrección» a lo que ya hacen F-11/G-26/G-27. Antes haría falta una
definición común para todas las tareas y pruebas contra respuestas generadas
erróneas. No adoptar reglas específicas ni enseñarle hechos que se inventó.

### 3. Reducer — ahorro posible, no remedio de comprensión

Cropper y Cerna, **AAAI 2026**; versión del 23 de enero:
[artículo completo v3](https://arxiv.org/html/2502.01232v3),
[publicación](https://ojs.aaai.org/index.php/AAAI/article/view/38972).
Descarta reglas con condiciones redundantes o incapaces de separar negativos,
bajo restricciones formales. Compara con Popper y dos ablaciones en 449 tareas:
reduce significativamente el tiempo en 96 y lo aumenta en cuatro; el 99 % es
un caso favorable. Presupuestos de 60 minutos por tarea, diez repeticiones,
un núcleo; coste medio de comprobar redundancia 2 %, máximo 80 %. Parte de
conocimiento formal previo y negativos, con supuesto de mundo cerrado.

**Inferencia para Leobot:** serviría si construir reglas fuese el gasto que
impide aprender. El obstáculo documentado ahora es representar el significado.
Ya existe eliminación de programas equivalentes; lo distinto por comprobar
serían las implicaciones entre condiciones y la poda demostrable de familias
enteras. No importamos su supuesto de que lo no conocido sea falso al kiosco.

## Decisión y criterios

| Idea | Diferencia frente a lo ya intentado | Prueba que decidiría |
|---|---|---|
| Asignaciones conjuntas | Restringir la combinación completa aprendida; conservar el modelo local G-24 | G-71: +0,03 F1 y +5 puntos de conjuntos completos, sin perder precisión |
| Hipótesis recursivas y ejemplos discriminantes | Ampliar de forma común lo que puede inventar el aprendiz, no solo elegir consultas | Preregistro futuro: tareas humanas nuevas, negativos externos y control sin ejemplos generados |
| Descartar familias redundantes | Deducir restricciones entre condiciones, además de eliminar programas iguales | Solo si un perfil de costo lo justifica: mismas respuestas y menos búsqueda, con costo de poda incluido |

La primera se ejecuta como [G-71](../prereg/G-71-construcciones-conjuntas.md).
La segunda y la tercera **no han sido probadas aquí**. No se incorporan por
su fecha ni por sus resultados ajenos. Tampoco se reabren ARC ni las variantes
de coincidencias/confianza G-65–G-70. El motor sigue congelado durante la prueba.

## Resultado de la primera adaptación

G-71 no pasó. En dos particiones, F1 de participantes subió aproximadamente
1,5 puntos, pero al barajar los enlaces educativos obtuvo prácticamente lo mismo.
No demuestra la capacidad buscada. Reinicio y renombrado pasaron; la medición
parcial fue rápida en el percentil 95, aunque hubo máximos superiores a cinco
milisegundos. Los detalles y costos están en el preregistro. No se probó en
G-71 la red de compatibilidad entre verbos y construcciones.

## Segunda adaptación: compatibilidad aprendida

[G-72](../prereg/G-72-compatibilidad-aprendida.md) prueba una transferencia propia
de esa compatibilidad mediante perfiles estructurales de verbos. Usa frases de
documentos educativos separados, ocultando sus etiquetas semánticas. En ambas
particiones, la calibración prefirió prescindir del mecanismo: mismo resultado
que G-71, sin aporte. No se promueve. Las dos adaptaciones costaron 30,72 s CPU
en sus cuatro corridas finales, hasta 149,6 MiB; excluye la descarga/interrupción
inicial registrada. No refutan toda la propuesta de los autores, que es distinta
y depende de capacidades que no se copiaron.

## Pista adicional sobre la educación que falta

Como antecedente anterior pertinente se revisó
[QANom, COLING 2020](https://aclanthology.org/2020.coling-main.274/), con
[datos y código de sus autores](https://github.com/kleinay/QANom). Sus preguntas
anotadas por personas vinculan participantes de acciones expresadas como
sustantivos con preguntas formuladas mediante verbos: más de 10 000 frases
y 26 000 pares en inglés. El sistema publicado usa BERT, recursos léxicos y
reglas de sufijos manuales; esos componentes no son adoptables aquí. Además,
excluye varias relaciones nominales que no provienen de verbos. No demuestra
resolver encabezados como «Horario» ni transferencia al español sin educación.

**Inferencia pendiente:** buscar educación humana que identifique la misma
relación en preguntas, verbos, expresiones nominales y condiciones; comprobar
primero disponibilidad y cobertura en español. La novedad por probar sería
esa correspondencia de significado con participantes y condiciones, no otra
tabla de sinónimos ni más pares aislados como G-65. No se encontró y verificó
todavía una fuente española equivalente en esta revisión. No se declara
agotada su búsqueda ni bloqueado el proyecto; debe preceder a un nuevo diseño.

## Fuente española localizada después

La búsqueda posterior encontró las publicaciones de
[AnCora-Nom](https://aclanthology.org/J12-4005/) e
[IARG-AnCora](https://clic.ub.edu/corpus/en/iargancora). Describen sentidos
nominales y participantes implícitos con revisión humana de anotaciones
automáticas. G-73 no pudo comprobar sus archivos: ambos enlaces oficiales
rechazaron la descarga con HTTP 403. Su puerta de contenido quedó sin evaluar.

Sí se obtuvo [Predicate Matrix 1.3, LREC 2016](https://aclanthology.org/L16-1423/)
desde [sus autores](https://adimen.ehu.eus/web/PredicateMatrix), con TLS normal.
Integra predicados y papeles de varias fuentes, incluyendo AnCora-Verb y
AnCora-Nom. Su método mezcla correspondencias anteriores y ampliaciones
automáticas: no es educación humana infalible ni un equivalente del corpus.

El conteo propio [G-73b](../prereg/G-73b-fuente-correspondencias.md) encontró
2 684 sentidos nominales españoles con candidatos verbales al unir predicado
y papel compartidos. Hay 17 459 pares candidatos; 2 454 sentidos nominales
tienen varios destinos. Solo tres sentidos nominales y siete verbales anotan
explícitamente tiempo. No contiene frases ni preguntas humanas.

La fuente sirve para investigar hipótesis que preserven participantes; copiar
sus enlaces como equivalencias seguras sería injustificado. Falta aprender a
elegir entre significados con evidencia del texto y medir el aporte frente a
un simple diccionario. No se entrenó el motor ni mejoró su cifra de utilidad.
