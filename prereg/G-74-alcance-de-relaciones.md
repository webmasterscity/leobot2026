# G-74 — alcance de una explicación por relaciones compartidas

2026-09-27. Registro previo al código. Motor estable
`11a1ef5836382d81a643cad0b217a8669ce0f2d1`; base educativa sin modificar.

## En palabras fáciles de entender

La fuente encontrada puede relacionar expresiones distintas, pero no sabemos
si esas relaciones aparecen en los fallos reales. Antes de construir el
aprendiz, mediremos un límite favorable: cuántas respuestas podría recuperar
si siempre eligiera bien entre todas las relaciones posibles. Si ni ese límite
ofrece una mejora suficiente, esta vía no merece un aprendiz más complejo.
Usaremos pruebas antiguas para este diagnóstico, sin llamarlas preguntas nuevas.

## Familia de mecanismo y límite que se mide

Se estudia un mecanismo que añade evidencia cuando una palabra de la pregunta
y otra distinta de la unidad de respuesta comparten un predicado de PropBank
en Predicate Matrix. Solo puede activar una propuesta nueva si esa evidencia
no literal está presente en la unidad propuesta. Posteriormente un aprendiz
debería elegir sentidos y comprobar participantes; aquí se le concede acertar
siempre esas decisiones. La referencia puede conservar todos sus aciertos.

Esto acota **esta familia activada por evidencia no literal**. No acota todos
los posibles usos de la fuente, ni los lectores que descartan una mala unidad
sin nueva evidencia en la unidad correcta, ni el aprendizaje general.
Fuente y límites en G-73b; G-34 añadía un diccionario léxico sin desambiguación.
G-71/G-72 no demostraron comprender relaciones. No reimplementarlos para pasar.

## Datos y cómputo fijados

- Predicate Matrix SHA
  `4630d1c9aa74e1012238167d43d0a6707589dad8873993d1c023d6e69652f781`.
  Leer las columnas ya fijadas en G-73b. Derivar lema de la forma
  `lema.número.variante` del identificador. Informar formatos desconocidos.
  Mantener todas las alternativas, sin filtrar palabras para el negocio.
- Base `.leobot-data/base_kiosco.json`, SHA
  `6fff61c20fcd5812d785eec22b6c595e19568f98ec31559e689c7fb95fe6d79f`.
  Reutilizar su normalización y lematización aprendidas.
- Bancos G-62/G-63/G-64: material gastado. Reproducir mediante `Bot.answer`
  las 816 preguntas directas/sí-no y sus 269 respuestas útiles por claves.
  Mantener historial por conversación y contar 488 preguntas sin dato aparte.
  Es conteo automático por claves, no juicio humano de utilidad o engaño.
- Para cada unidad, texto más encabezado heredado según el motor actual.
  Un enlace nuevo exige lemas diferentes y que el lema preguntado no esté
  literalmente en esa unidad. No se añade texto a las respuestas.
- Límite léxico: compartir cualquier predicado. Límite con casillas: compartir
  predicado **y** al menos un código de participante en la fuente. Este segundo
  tampoco comprueba quién cumple el papel en el texto: es deliberadamente
  favorable al mecanismo futuro. No llamarlo comprensión de participantes.
- Para cada pregunta, conceder corrección si la referencia ya contesta con
  todas las claves, o si alguna unidad con todas las claves tiene enlace nuevo.
  Contar ganancia máxima, lemas/preguntas cubiertos, vínculos nominal-verbo y
  preguntas sin dato que también activarían el mecanismo. No guardar frases
  de los bancos como educación.

## Puertas y decisión

Si el límite superior con casillas queda por debajo del 60 %, declarar que
esta familia no podría alcanzar sola esa meta en este banco, aunque aprendiera
perfectamente. Si además la mejora máxima es <5 puntos porcentuales, descartar
su implementación para el kiosco actual. Si hay ≥5 puntos posibles, preregistrar
un aprendiz condicionado por evidencia textual y comprobar la mejora real,
no sustituirla por este límite. No se decide usando la panadería del usuario.

Control: motor sin cambios y referencia pública con conteos históricos iguales.
No corresponde señal barajada: se calcula disponibilidad, no rendimiento de
un aprendiz. No hay promoción, reserva, generación de hechos ni prueba de AGI.

## Presupuesto y ejecución

≤120 s CPU para adquirir/preparar, ≤120 s para diagnóstico, ≤1 GiB RAM y
≤300 s transcurridos. No nuevas descargas. Registrar costos por fase, unidad
de las métricas y huellas antes/después. Commit del registro antes del código,
y tag `freeze-G74-alcance` antes de evaluar.

```bash
timeout 300s env PYTHONHASHSEED=0 python3 -m experiments.g74_relation_coverage
```
