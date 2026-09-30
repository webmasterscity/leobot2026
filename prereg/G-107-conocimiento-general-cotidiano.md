# G-107 — Conocimiento general cotidiano desde recursos humanos (pedido del usuario, 2026-09-29)

Fecha: 2026-09-29. Estado: diseñado (precede al código). Motor de partida: `fa15c4a` (huella `2d651fbd…`). Comparte con G-106 el
almacén de saber general (`leobot/knowledge.py`); se congela junto con él.

## Pedido y medida
El usuario pide «por lo menos un 1000 % más» de conocimiento básico, general, útil y de vida cotidiana.
Línea base medida hoy (`base_kiosco_nube.json`): **0 hechos, 0 reglas, 0 frases leídas**; `respond` contesta «No lo sé» a
«¿Para qué sirve un paraguas?», «¿El gato es un animal?», etc. Un 1000 % de cero no mide nada, así que se informan dos medidas:
- **cantidad**: relaciones de saber general guardadas, de fuentes humanas (línea base 0; meta ≥ 100 000);
- **capacidad**: preguntas nuevas de conocimiento cotidiano contestadas bien, con juez (línea base 0).

## Qué fallo concreto resuelve
Sin conocimiento general el bot no puede contestar nada cotidiano, y la lectura no encadena: sabiendo «el perro es un mamífero» y
«el mamífero es un animal» no contesta «¿El perro es un animal?». Además el contraste de G-46 puede decir un «No» falso
(«No: es un mamífero») cuando falta el eslabón. Clasificación prevista: lo literal es «no sabía» (falta información); lo encadenado
es «no pudo» (falta mecanismo).

## Por qué los mecanismos actuales no bastan
- La lectura literal contesta bien desde frases, pero guardar el saber como frases no cabe: tope de 200 000 frases, límite de
  carga de 100 MiB (la base ya ocupa 90) y cada relación necesitaría varias frases.
- El aprendiz de construcciones (`language.teach`) necesita un marco anotado por cada forma de pregunta.
- No hay inferencia encadenada en la ruta de lectura.

## Mecanismo
1. **Almacén** (`leobot/knowledge.py`, el mismo de G-106): relaciones entre términos con su fuente, en índices compactos.
   Fuentes (humanas, licencia abierta, SHA registrados): WordNet español (MCR/OMW 1.4 sobre PWN 3.0) con los tipos de relación
   que ConceptNet ya asigna a WordNet (IsA, PartOf, Synonym, Antonym…); ConceptNet 5.7 en español; sentido común de Open Mind en inglés
   con los dos extremos de una sola palabra y traducción humana inequívoca (ver G-106).
2. **Plantillas humanas.** Para cada relación, todas las plantillas en español que escribieron las personas de Open Mind
   (`surfaceText` de ConceptNet con los extremos quitados: «Se usa [] para []», «[] es parte de []»…). Una relación sin plantilla
   humana en español no se usa para contestar en `respond` (sí para G-106).
3. **Qué relación pide una pregunta.** Se quitan de la pregunta los términos que están en el almacén; los términos que quedan se
   comparan con las palabras fijas de cada plantilla (lemas, con peso por rareza entre plantillas). Gana la relación con más
   coincidencia, si la hay y si el término conocido tiene relaciones de ese tipo; si hay empate entre relaciones, no se contesta.
   Con un término conocido se contesta el otro extremo; con dos se verifica (sí/no).
4. **Encadenar.** Una relación se encadena si su tasa de transitividad **medida en los datos** (caminos a→b→c cerrados por a→c
   afirmado, en ConceptNet) es ≥ 0,05 y ≥ 5 veces la mediana de las demás relaciones; máximo 6 pasos. «¿X es un Y?» se contesta
   «Sí» si Y está en la cadena, mostrando la cadena.
5. **Sin «No» falso.** Si el conocimiento general sabe que el valor dicho está incluido en el preguntado (cadena de inclusión), el
   contraste de G-46 no contesta «No». Solo se contesta «No» desde el saber general cuando hay una afirmación negativa (Antonym,
   NotCapableOf, etc.) o dos clases hermanas **ambas** con la relación de inclusión; si no, «No lo sé».
6. **Dónde entra.** En `respond`, después de la lectura literal y solo si esta no encontró nada (lo que dijo la persona manda). La
   respuesta dice de dónde sale («Por lo que sé en general…») y verbaliza con la plantilla humana; nunca se inventa texto.
   `Bot.answer` del kiosco **no** usa esta ruta (el negocio se contesta solo desde su texto).

## Qué eliminaría si funciona
Nada del motor; sustituye la necesidad de enseñar frases sueltas para el saber cotidiano.

## Experimento que distingue las hipótesis
Banco **nuevo** de preguntas de conocimiento básico y cotidiano, escrito después de congelar el motor por redactores independientes
(Agent con `isolation: "worktree"`, nunca *fork*; encargo neutral: «preguntas que una persona adulta corriente sabría contestar sobre
el mundo cotidiano, con su respuesta breve; y algunas que no se pueden contestar sin datos particulares»; sin este preregistro, sin las
fuentes ni la lista de relaciones, sin mensajes del usuario, sin ejemplos). Al menos 300 preguntas de al menos 6 redactores de al
menos 2 familias de modelo. Juez ciego doble con desempate: correcta, parcialmente correcta, abstención, equivocada.
Sistemas: bot sin saber (línea base); tratamiento; saber barajado (destinos permutados dentro de cada relación); sin encadenar;
reinicio; `PYTHONHASHSEED` 0 y 1.

## Umbrales de éxito (fijados ahora)
1. Correctas (juez) ≥ 15 % de las preguntas contestables del banco; línea base 0.
2. Entre las respuestas dadas (no abstenciones), correctas o parcialmente correctas ≥ 80 %.
3. Saber barajado: correctas ≤ un tercio de las del tratamiento.
4. Encadenar aporta en sus casos (preguntas de inclusión): tratamiento > sin encadenar; «No» falsos del saber general = 0 en
   preguntas cuya respuesta es «sí».
5. `respond`: p95 ≤ 10 ms con el saber cargado; RAM adicional ≤ 300 MB; base ≤ 100 MiB; reinicio y hashseed idénticos.
6. Cantidad: ≥ 100 000 relaciones de fuentes humanas guardadas (frente a 0).
Si 1 o 2 fallan, no se promueve; se conserva el resultado y se clasifica cada fallo en «no sabía» / «no pudo».

## Presupuesto
Construir el saber ≤ 10 min de CPU; sin red durante la respuesta.

## Riesgos declarados
- Las fuentes alcanzables desde el contenedor son sobre todo léxicas (WordNet, Wiktionary); el sentido común traducido es pequeño
  (≈ 6 000 aserciones). Wikipedia, Wiktionary en español, Tatoeba y DBpedia están bloqueados por la red del entorno.
- Las plantillas de Open Mind en español son pocas (≈ 100 ejemplos) y a veces torpes; se usan tal cual.
- Las traducciones eligen el sentido más votado, no el del contexto.
