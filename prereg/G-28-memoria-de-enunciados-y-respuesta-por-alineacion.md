# G-28 — memoria de enunciados y respuesta aprendida por alineación con hueco

Fecha: 2026-09-23. Preregistro previo al código. Base `estable-G-2:leobot` = `df4c9e96ae803c2fc25475d69be9b8e73013e621`.

## Fallo concreto y causa de fondo

[CMP-1](cmp-1-leobot-frente-a-subagente.md): con el mismo párrafo y la misma pregunta, un subagente Claude acierta 12/20 casos MLQA (F1 0,77) y 4/4 en la sonda; Leobot 0/20 y 0/4, aunque en la sonda la respuesta está literalmente en la frase leída. Causa: Leobot solo guarda lo que ya sabe convertir en relación. Una frase cuya superficie no se repite tres veces (o no encaja en un marco léxico V5.20) queda `raw_relation_pending` y **no se guarda nada**; después, una pregunta sin construcción aprendida es `unrecognized`. Una persona sí puede responder «¿Qué manda sobre la ambición?» tras leer «La evidencia manda sobre la ambición» sin saber qué significa «manda»: recuerda el enunciado y alinea la pregunta con él. Esa capacidad falta en el motor.

## Hipótesis y alternativa

(a) Guardar cada enunciado declarativo leído, con procedencia e índice por palabra, y (b) aprender **de ejemplos resueltos de otros textos** —texto, pregunta y respuesta, como demostración— qué palabras de una pregunta marcan el hueco y qué forma y posición tiene la respuesta respecto de lo alineado, permite responder preguntas nuevas sobre textos nuevos citando el fragmento y su fuente, o abstenerse. Alternativa: la alineación sola explica todo el acierto (el aprendizaje no aporta), o el acierto viene de coincidencias léxicas memorizadas (se rompe al renombrar), o no supera un nivel trivial.

Antecedentes: alineación pregunta–oración y extracción de respuesta sin redes ([Yao y otros, NAACL 2013](https://aclanthology.org/N13-1106.pdf)); línea base fuerte de alineación ([Kamath y otros, 2018](https://arxiv.org/pdf/1807.01836)); ventana deslizante en SQuAD ≈0,20 F1 ([Rajpurkar y otros, 2016](https://arxiv.org/abs/1606.05250)). Ninguno demuestra este mecanismo en Leobot.

## Mecanismo (5.8)

- **Qué fallo resuelve:** 0/20 y 0/4 con la respuesta presente en el texto.
- **Por qué no bastan los actuales:** la inducción cruda exige superficies repetidas y el tablero entrega un solo párrafo; las construcciones de pregunta dependen de relaciones ya inducidas.
- **Qué lo distingue:** ablación sin modelo aprendido, educación barajada, bot fresco, renombrado.
- **Qué eliminaría si funciona:** nada todavía; si en un ciclo posterior la memoria de enunciados alimenta la inducción cruda, reemplazaría la lista de observaciones crudas por este índice.

Reglas de diseño: sin listas de palabras del español en el código nuevo (los marcadores del hueco se aprenden de los ejemplos); solo clases de caracteres (mayúscula, dígito) y tokenización; pesos de palabra por frecuencia aprendida de la propia memoria; respuesta marcada como **lo que dice el texto** (`literal`), con enunciado y fuente, nunca como hecho verificado; abstención si el margen no alcanza un umbral calibrado en la educación. Todo por interfaces públicas: `ingest_document_text`, una demostración `observe_reading_example(texto, pregunta, respuesta)` y `respond`.

## Datos y partición

Archivo MLQA con SHA fijado en el tablero. **Educación:** 2000 ejemplos de `test-context-es-question-es` elegidos con semilla 2828; **desarrollo visible:** otros 300 del mismo archivo. **Reserva:** 200 preguntas de `dev-context-es-question-es`, excluidos los 20 del tablero, elegidas con los primeros 8 hexadecimales de `git rev-parse freeze-G-28:leobot`, generadas tras congelar. Se comprueba que ningún párrafo de reserva aparece en la educación. Los 20 del tablero y la sonda se informan aparte como diagnóstico.

## Controles

Tratamiento educado; **fresco** (sin ejemplos: debe abstenerse siempre); **ablación** (misma memoria y alineación, respuesta = tramo no alineado más cercano de longitud 1–3, sin modelo aprendido); **educación barajada** (cada respuesta emparejada con la pregunta de otro ejemplo); **renombrado** (en cada caso de reserva, cada palabra presente a la vez en párrafo y pregunta se sustituye por una palabra inventada que conserva mayúscula y dígitos); **honestidad** (cada pregunta frente al párrafo de otro caso: debe abstenerse); **reinicio** (guardar/cargar conserva las salidas); **memoria conjunta** (los 200 párrafos en un solo bot: la pregunta debe encontrar su enunciado).

## Puerta (por hashseed 0 y 1, con salidas idénticas)

- Reserva educada: **F1 ≥ 0,25 y exactas ≥ 0,10**.
- Ventaja ≥ 0,05 F1 sobre la ablación y ≥ 0,10 sobre la educación barajada.
- Fresco: 0 respuestas. Honestidad: ≥ 90 % de abstenciones.
- Renombrado: F1 a ≤ 0,03 del tratamiento. Reinicio: salidas idénticas.
- Memoria conjunta: F1 ≥ 0,8 × la del tratamiento.
- Latencia por pregunta p95 ≤ 10 ms con un párrafo y ≤ 200 ms con memoria conjunta; educación ≤ 60 s CPU; RSS ≤ 256 MiB.
- Pruebas rápidas y regresión completa sin fallos nuevos antes de cualquier tag; prueba de latencia fija sin empeorar > 20 %.

Si falla, no se relaja: se registra y se analiza la causa. Un éxito mostraría que Leobot puede recordar y citar lo leído y aprender a responder de ejemplos; **no** mostraría comprensión, inferencia ni paráfrasis profunda, y el subagente seguiría por delante (0,77 F1).

## En palabras fáciles de entender

Hoy Leobot olvida casi todo lo que lee, porque solo guarda lo que ya entiende. Vamos a hacer que guarde cada frase que lee, con su origen, y que aprenda, mirando ejemplos resueltos de otros textos, a encontrar en una frase el pedazo que responde una pregunta. Lo examinaremos con textos y preguntas que nunca vio. Si no sabe, debe decir «no sé».
