# G-99 a G-101 — entrenamiento propio y prueba de Model2Vec

2026-09-27. Tres ensayos terminados. La meta sigue sin alcanzarse; versión estable intacta.

## En palabras fáciles de entender

Seguimos mejorando el modelo propio y probamos tu sugerencia de Model2Vec.
Primero enseñamos a conservar coincidencias precisas entre palabras y a mirar
la pregunta anterior. Después dimos una etapa adicional de práctica con
negocios. Ambos intentos acabaron diciendo «No lo sé» igual que la versión
estable en las preguntas que esta ya dejaba sin responder.

Model2Vec sí funciona rápido en este equipo. Ayuda a comparar textos por su
significado, pero que dos textos se parezcan no demuestra que uno conteste al
otro. Lo combinamos con un selector entrenado por nosotros y con una confianza
ajustada usando ejemplos separados. El resultado fue 31 respuestas útiles de
102 y siete citas equivocadas nuevas. El prototipo G-98 daba 32 y también
siete equivocadas nuevas: esta combinación no lo superó.

Al exigir mayor confianza, vuelve a las 29 respuestas útiles de la versión
estable y evita añadir errores, porque la ayuda no responde. Eso tampoco cumple
la meta. En la panadería, la combinación menos restrictiva encuentra el horario,
mantiene cheques correcto y estacionamiento desconocido, pero no la dirección.

Mi recomendación es mantener Model2Vec como una opción experimental. No usar
su semejanza como porcentaje de certeza. El trabajo pendiente está en aprender
a elegir la frase que satisface lo preguntado, incluyendo sus condiciones,
y comprobar cuándo el documento realmente carece del dato. No hay fundamento
para reemplazar hoy el modelo propio por esta combinación ni para anunciar 60 %.

## Comparación de respuestas

Mismo material gastado: seis negocios y 157 turnos, 102 con dato en el texto,
47 sin dato y ocho de otras clases. Juicio automático por claves, sin cambiarlo.
No es un nuevo examen independiente ni el banco del 35,9 % histórico.

| Variante | Útiles / 102 | Errores nuevos frente al estable |
|---|---:|---:|
| Leobot estable | 29 | Referencia |
| Prototipo propio G-98 | 32 | 7 |
| G-99: cuatro decisiones nuevas, ambos mínimos | 29 | 0, no añade respuestas |
| G-100: nueve adaptaciones, ambos mínimos | 29 | 0, no añade respuestas |
| Model2Vec solo + confianza ajustada, G-101 | 29 | 0, no añade respuestas |
| Model2Vec + selector propio, mínimo 0,4 | **31** | **7** |
| Model2Vec + selector propio, mínimo 0,9 | 29 | 0, no añade respuestas |
| Model2Vec + selector con preguntas mezcladas | 29 | 0, no añade respuestas |

Los mínimos 0,4 y 0,9 se fijaron antes de medir. La principal de G-101 era
la combinación a 0,9; la alternativa 0,4 también estaba prevista. No se eligió
un mínimo después de ver el resultado. Cero errores nuevos no significa que
el estable tenga cero errores: conserva sus 12 citas incorrectas con dato y
siete citas ante falta de dato, según el evaluador.

[G-99](g99_common.json), [G-100](g100_common.json), [G-101](g101_common.json).

## Qué aprendimos sobre elegir y confiar

Entre las 61 preguntas con dato que el estable deja sin responder, su candidata
interna original contiene las claves en 22 casos. G-98 elige bien ocho; G-99,
con coincidencias precisas, 19; G-100 adaptado a negocios, 13. Model2Vec solo
elige bien 18 y combinado con nuestro selector, 19. La semejanza aporta frente
al selector G-98, pero no supera aquí la candidata interna original.

El salto educativo tampoco basta: la combinación Model2Vec elige bien 981/1534
fragmentos en la comprobación educativa, frente a 893 de Model2Vec solo. Es otra
tarea, con otra distribución; **no equivale a 64 % de respuestas útiles del kiosco**.

La confianza de G-101 se ajustó con 455 propuestas de negocios separados de
los usados para enseñar. Model2Vec solo acertó 79 y la combinación 94. Sus
confianzas máximas aprendidas fueron 0,36 y 0,4082. Es una estimación empírica,
no una garantía. Una semejanza de 0,9 no se interpreta como 90 % de acierto.

Los errores cuadráticos de confianza están en `raw_choices` de G-101 como
diagnóstico. No se usan para ordenar modelos: las etiquetas cambian cuando
cada variante propone una cita diferente, y un selector casi siempre equivocado
puede obtener un error pequeño prediciendo baja confianza. Tampoco se usaron
para retocar pesos o mínimos después de medir.

## Entrenamiento y fuentes

- G-99 conserva las representaciones de G-98 y aprende decisiones pequeñas
  sobre coincidencias, correspondencias aprendidas, comparación por palabra y
  pregunta previa; controles sin representación neuronal/historial y preguntas
  confundidas. Enseñanza general mejora, pero no la utilidad del kiosco.
- G-100 conserva esas redes y aplica 24 épocas adicionales con 1737 ejercicios
  de negocios; controles con 1737 textos generales y preguntas confundidas.
  La mejora de 76 a 84 propuestas correctas en calibración no se transfiere a
  las preguntas comunes. No se bajó 0,4 para aceptar su máximo 0,3958.
- G-101 usa [potion-multilingual-128M](https://huggingface.co/minishlab/potion-multilingual-128M),
  revisión `73908c3438cf03b6a01bcb9611d62b23d0726f08`, con
  [Model2Vec](https://github.com/MinishLab/model2vec) 0.9.0. La representación
  preentrenada se mantiene congelada; se enseña una decisión de 865 parámetros.
  No es un modelo de lenguaje entrenado desde cero por nosotros.
- G-101 reutiliza 6000 preguntas humanas SQAC y 1737 ejercicios sintéticos
  de negocios de enseñanza. Grupos de enseñanza, comprobación y confianza
  separados, con las mismas huellas de G-98. Ninguna pregunta del examen común
  ni la panadería se usó para enseñar. No se hizo reserva nueva al fallar desarrollo.

La revisión de [ColBERT](https://arxiv.org/abs/2004.12832),
[K-NRM](https://arxiv.org/abs/1706.06613) y
[SmallReason-ColBERT v1, agosto 2026](https://arxiv.org/html/2609.29652v1)
motivó comparar por palabras y aprender pesos. Se comprobaron métodos,
controles y costos; sus resultados con otras redes/datos no demuestran esta
adaptación ni el presupuesto local. Las hipótesis y fuentes preceden al código:
[G-99](../prereg/G-99-interaccion-y-dialogo-aprendidos.md),
[G-100](../prereg/G-100-adaptacion-educativa-por-etapas.md),
[G-101](../prereg/G-101-model2vec-y-confianza-aprendida.md).

## Tiempo, memoria y costo

En G-101, respuesta completa de la combinación a 0,4: p95 1,864 ms y máximo
2,144 ms; repetición 1,891/2,161 ms. A 0,9: 1,933/2,141 ms; repetición
2,396/3,490 ms. También las llamadas donde actúa la ayuda quedan bajo 5 ms.
Son tiempos con modelo y documento cargados; carga y preparación se pagan aparte.

La carga preliminar de Model2Vec tardó 1878 ms. Codificar 40 frases distintas,
sin responder preguntas, tuvo mediana 0,065 ms y máximo 3,230 ms. Esa medida
aislada no sustituye a `Bot.answer`. Descarga local: 530 985 602 bytes; entorno
virtual separado, sin modificar paquetes globales, GPU ni servicio de inferencia.

| Ensayo | CPU de preparación, enseñanza y confianza | Memoria máxima de enseñanza |
|---|---:|---:|
| G-99 | 71,342 s | 1,73 GiB |
| G-100 | 44,975 s | 1,32 GiB |
| G-101 | 49,375 s | 2,15 GiB |

La repetición de G-99 con historial tuvo p95 5,684 ms y máximo 7,954 ms: ese
límite tampoco pasó y el resultado se conserva. No se atribuye el pico a una
causa no medida. G-100 principal sí queda bajo 5 ms en ambas corridas.

Costo nuevo instrumentado de las tres pruebas, incluida adquisición, medidas,
repeticiones y comprobaciones finales: **al menos 277,074 s CPU**. Algunas
lecturas, pruebas iniciales y creación del entorno no midieron CPU. Costos de
la base, textos y modelos G-97/G-98 reutilizados. Cierres detallados:
[G-99](g99_closure.json), [G-100](g100_closure.json), [G-101](g101_closure.json).

## Comprobaciones y decisión

Pasaron 24 pruebas finales. Respuestas idénticas en procesos nuevos con otro
orden de hashes: diez variantes G-99, veinte G-100 y ocho G-101. Desactivación,
cambio/vaciado de documento, exportación numérica y huellas pasan. Model2Vec
comparte una sola tabla de solo lectura. Motor, base y modelos anteriores
intactos. [Comprobaciones compartidas](g99_g100_g101_integration.json),
[comprobaciones G-101](g101_checks.json).

Con G-101 a 0,4, tu panadería devuelve horario y cheques, calla sobre
estacionamiento y sigue sin dirección; máximo 0,622 ms. Con 0,9 la ayuda se
abstiene. [Caso exacto](g101_user_diagnostic.json).

**No se incorpora ningún candidato al estable.** Model2Vec queda disponible
para pruebas, pero el siguiente esfuerzo debe mejorar conjuntamente selección
y comprobación del respaldo de la respuesta. Los datos actuales no justifican
reemplazar G-98 por la combinación ensayada, ni prometer que más épocas logren
60 %. Se mantiene abierta la meta y se conservan los resultados negativos.

Reproducir G-101 con los archivos locales, escogiendo una salida nueva:

```bash
timeout 240s env PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false .leobot-data/g101/venv/bin/python -m experiments.g101_evaluate --output /tmp/g101_reproduccion.json
```

Modelos G-101 congelados antes de medir: `freeze-G101-prototipo` / `79771ba`.
Fuentes, revisiones y huellas en los registros de adquisición y enseñanza.
