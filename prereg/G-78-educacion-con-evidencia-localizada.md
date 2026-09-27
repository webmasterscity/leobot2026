# G-78 — educar el mecanismo existente con evidencia localizada por personas

2026-09-27, previo a código. Motor `11a1ef5836382d81a643cad0b217a8669ce0f2d1`.

## En palabras fáciles de entender

Hasta ahora el mecanismo que busca respuestas aprende sobre todo de preguntas
frecuentes con respuestas largas. En ellas hay palabras que no responden a la
pregunta. Probaremos si aprende mejor cuando una persona ya ha señalado dónde
está el dato. Le daremos la oración que contiene ese dato y otra oración del
mismo texto, para que cuente qué las distingue. No se escribirán significados
de horarios, pagos ni negocios. Las respuestas continuarán saliendo del texto
del negocio, y se medirá si esta educación sirve en negocios diferentes.

## Antecedentes y causa candidata

G-67 eligió oraciones de MFAQ con el lector existente: etiquetas débiles que
dependen de ese lector. G-69 cambió asociaciones con la misma fuente MFAQ.
G-75–G-77 añadieron representación sin mejorar. F-4–F-9 ya usaron SQAC para
extraer fragmentos; esta fuente **no es nueva** ni se presenta como reserva.
Aquí se prueba una educación de selección de oraciones, con su ubicación
indicada por humanos, para las tablas estables de relevancia y confianza.

Fuente primaria: [ficha SQAC de sus autores](https://huggingface.co/datasets/PlanTL-GOB-ES/SQAC/blob/main/README.md),
descrita en MarIA (2022). Preguntas anotadas por hablantes nativos sobre textos
de Wikipedia, Wikinews y AnCora. Solo `train.json`, revisión
`f9928e8819596a601b8887cc5f8598b15d589a82`, SHA
`1d5c76176646e2ae7bdcd8b5ec6f18349102a9363aa25ad7d0e48262d7480d43`.
Archivo recuperado antes de este diseño: 11 042 089 bytes, 0,099 s CPU y 2,317 s
transcurridos. No se abrieron dev/test. Su ausencia de preguntas sin respuesta
impide usarlo solo para enseñar cuándo callar; eso sigue calibrándose en TRAIN.
La búsqueda también encontró ESQAD (2026), que mezcla ejemplos humanos y
generados por LLM; no se adopta para esta prueba.

No se propone un subsistema. Reutilizar conteos G-57/G-59: exceso de coincidencia
propia frente a rival, mínimo de apariciones 3, términos raros 1–5, puente con
apoyo en 20 grupos, elevación 4 y máximo 12 destinos. No cambiar esos valores.
Si funciona, sustituye parte de las tablas educativas; motor y formato intactos.

## Datos y variantes

Validar que la respuesta coincide exactamente con su posición anotada. Segmentar
el contexto con el separador de oraciones existente `_SENTENCE_END`, conservando
posiciones. Solo ejemplos cuya respuesta cabe en una única oración y con otra
oración que no contiene esa respuesta literalmente. Excluir el ejemplo de la
ficha ya excluido por F-4. Agrupar por origen y título; si falta título, usar la
huella del contexto. No usar preguntas del kiosco ni la panadería como educación.

Como máximo 10 000 ejemplos, ordenados por SHA del identificador. Por pregunta,
seleccionar una rival entre las oraciones sin respuesta por SHA de id/oración.
No usar un LLM ni el lector para etiquetar la oración positiva o sus significados.

Variantes con mismas preguntas y rivales:

- localizada: oración que contiene el tramo humano;
- párrafo: contexto completo como positivo, para medir el efecto de localizar;
- confundida: reemplazar la oración positiva por otra del pasaje que no contiene
  la respuesta, elegida con otro orden SHA. Es control de etiquetas, no una
  afirmación de falsedad de los hechos de la otra oración.

Las cuentas guardan solo términos y frecuencias; no frases ni respuestas. En
los 20 grupos de apoyo, SQAC cuenta artículos, mientras MFAQ contaba sitios:
se declara esa diferencia y no se atribuye independencia por editorial.

## Selección y puertas

Mezclar las tablas nuevas con las estables por pesos 0,25; 0,5; 0,75; 1 y cero.
Para cada término, interpolar delta usando rare_delta si no está registrado;
para cada vínculo, interpolar su peso, ausente equivale a cero. Conservar los
12 destinos más fuertes. Recontar confianza Bayes/isotónica G-68 con los mismos
7 rasgos; umbral 0,4. Cruce por negocio TRAIN G-68. Elegir por más útiles sin
aumentar citas sin dato, desempate por menos citas y menor peso. Control y
ablación se seleccionan por el mismo procedimiento.

Medir con `Bot.answer`, historial y DEV G-62/63/64 gastado. Puerta parcial:
≥5 puntos útiles sobre base, ≥2 sobre párrafo y ≥2 sobre confundida; citas sin
dato no mayores que base. Reinicio y desactivación exactos, citas literales,
p95 y máximo <5 ms. Informar selección sin abstención, exclusiones y costos.
Las claves automáticas no sustituyen al juez; reserva y revisión independiente
solo si pasa. No se declara resuelta la meta del 60 % por una puerta parcial.

## Presupuesto

Preparación/educación ≤300 s CPU, calibración/evaluación ≤200 s, ≤1 GiB RAM,
≤700 s transcurridos, un proceso pesado. Guardar tablas antes de evaluar y
registrar interrupciones. Pruebas focales de offsets, contraste y aislamiento;
comprobar equivalencia de conteos con la fórmula existente. Congelar como
`freeze-G78-prototipo` antes de medir, sin afinar criterios sobre DEV.
