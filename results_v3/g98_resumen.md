# G-98 — resultado del nuevo entrenamiento

2026-09-27. Tanda terminada; modelo experimental conservado, sin integración.

## En palabras fáciles de entender

Entrené otra vez el modelo de dos formas. Primero le di el doble de pasadas
por los ejemplos originales. Después probé una enseñanza más cercana a su
trabajo: elegir la frase que contesta dentro de un documento y reconocer
cuándo falta el dato. Separé documentos completos para enseñar y comprobar.

Repetir los ejemplos originales mantuvo 29 respuestas útiles de 102. La
enseñanza nueva consiguió 32, pero también produjo siete respuestas equivocadas
nuevas según el evaluador automático. El aumento de respuestas útiles fue del
10,3 %, acompañado de más errores: no alcanzamos el 100 % de mejora pedido,
que habría exigido 58 respuestas útiles, ni una mejora segura.

Sí hubo un avance concreto: ahora el modelo entrenado encuentra el horario de
tu panadería sin usar reglas manuales. Conserva la respuesta sobre cheques y
calla sobre estacionamiento. Todavía no encuentra la dirección. Es un resultado
del prototipo; el Leobot estable sigue igual.

El siguiente problema es que el modelo escoge frases parecidas que no responden
lo preguntado. Entre las 61 preguntas con dato que Leobot dejaba sin responder,
pasó de elegir bien seis fragmentos a ocho. Esa mejora pequeña no alcanza para
duplicar las respuestas útiles. Recomiendo conservarlo para estudiar sus fallos
y exigir más precisión antes de integrarlo. Esta tanda termina aquí.

## Qué se entrenó

- Modelo inicial: selector propio G-97 de 1 288 384 parámetros. Vocabulario y
  representación de 64 números conservados; no se descargó otro modelo.
- `more`: seis pasadas adicionales por los mismos 6000 pares MFAQ; doce en
  total contando G-97. Optimizador reiniciado según el preregistro.
- `localized`: doce pasadas sobre 6000 preguntas humanas SQAC con fragmentos
  anotados y 1737 ejercicios de negocios sintéticos previamente declarados como
  enseñanza. Entre estos últimos hay 562 casos sin dato. Se aprenden 65 parámetros
  adicionales para escoger una opción vacía: total 1 288 449.
- `shuffled`: mismo entrenamiento localizado, con preguntas mezcladas dentro
  de su grupo para romper las asociaciones correctas. Es un control.
- 1798 ejercicios separados de comprobación: 1000 humanos y 798 de negocios,
  1534 con dato y 264 sin dato. Grupos distintos de enseñanza y ajuste de confianza.
  La comprobación de documentos normalizados no encontró duplicados entre
  enseñanza, comprobación, confianza y los bancos de comparación.
- Confianza ajustada con 455 propuestas de negocios separados. Mínimo de 0,4
  fijado antes de entrenar, sin cambiarlo tras ver los resultados. No se enseñó
  con la panadería ni con las preguntas de la comparación común.

La separación se refiere a esta enseñanza adicional: Leobot y el modelo G-97
ya traían conocimiento previo. Estos ejercicios no son una reserva nueva de
negocios ni demuestran generalización. [Registro de enseñanza](g98_training.json).

## Comparación común

Mismo banco gastado de G-97: seis negocios, 157 turnos, de los que 102 tienen
respuesta y 47 carecen de dato. Evaluador automático anterior sin modificar.
No comparar estos porcentajes directamente con el 35,9 % histórico de otro examen.

| Variante | Útiles / 102 | Nuevas citas equivocadas | Tiempo del 95 % / máximo, ms |
|---|---:|---:|---:|
| Estable | 29 | Referencia | 0,394 / 0,877 |
| Modelo G-97 original | 29 | 0 | 0,597 / 12,742 |
| Doble de pasadas originales | 29 | 0 | 0,633 / 6,397 |
| Enseñanza localizada | **32** | **7** | **0,747 / 3,526** |
| Preguntas mezcladas | 29 | 0 | 0,698 / 0,867 |

Las siete nuevas citas equivocadas son cuatro ante preguntas con dato y tres
ante preguntas sin dato. Por ejemplo, preguntando por un teléfono de reservas
elige el precio de un taller; preguntando por Diners Club cita la restricción
de American Express. Las frases existen en el documento, pero no responden.

Cuando la ayuda localizada interviene, tiempo del 95 % / máximo: 0,838 / 3,525 ms.
Tiempos de respuesta completa con modelo y documento cargados, una hebra CPU;
preparación y carga aparte. En la repetición, 0,467 / 0,622 ms sobre todos los
turnos, y respuestas exactamente iguales en las cinco variantes. Se conservan
los máximos de la primera corrida, incluidos los que superan 5 ms en las otras
variantes; no se atribuyen a una causa que no se midió.

[Primera medición](g98_common.json), [repetición en proceso nuevo](g98_common_restart.json).

## Qué mejoró y qué sigue fallando

En la comprobación educativa, la elección cruda acertó 543/1534 con enseñanza
localizada, frente a 421 con más pasadas originales y 411 con preguntas mezcladas.
Ese avance educativo no se traslada con igual fuerza al kiosco:

| Sobre 61 preguntas con dato que el estable deja sin responder | Fragmentos elegidos correctamente |
|---|---:|
| G-97 | 6 |
| Más pasadas originales | 8 |
| Enseñanza localizada | 8 |
| Preguntas mezcladas | 4 |

La opción vacía aprendida se elige en 23/40 preguntas sin dato, pero también
en 13/61 que sí tienen dato. Con las elecciones actuales, aun aceptando solo
las ocho propuestas correctas, el techo optimista en esta muestra sería
29 + 8 = 37/102. Ajustar únicamente la confianza no permitiría llegar a 58.
El selector aún ignora el historial, límite declarado antes de entrenar.

## Panadería y comprobaciones

El modelo localizado cita «Horario: lunes a sábado de 7:00 a 19:00.» para
«¿A qué hora abren?». Mantiene cheques correcto y estacionamiento desconocido;
dirección sigue desconocida. Dos respuestas útiles de tres posibles frente
a una del modelo anterior. Máximo observado: 0,391 ms.
[Respuestas completas](g98_user_diagnostic.json).

Pasaron 19 pruebas, exportación numérica equivalente, desactivación exacta,
cambio de documento sin citas antiguas, documento vacío y recarga en proceso
nuevo con distinto orden de hashes. Al cambiar el horario de un documento,
la respuesta cita el nuevo dato. [Comprobaciones](g98_checks.json).

## Costo, decisión y propuesta

Preparación, tres entrenamientos, comprobación educativa y confianza: **125,371 s
de CPU**, 150,643 s transcurridos desde el inicio de la función de enseñanza;
las importaciones previas están incluidas en CPU, no en ese reloj de pared.
Pico registrado: 1 150 268 KiB, aproximadamente 1,10 GiB.
Comparación, panadería y repetición: 19,191 s de CPU, incluyendo importaciones
y examen de elecciones crudas. Suma nueva instrumentada, incluidas pruebas
finales y comprobaciones de integración: **al menos 157,505 s CPU**. Algunas
comprobaciones iniciales pequeñas no midieron CPU. Costos anteriores de G-97,
la base y adquisición de textos reutilizados; sin nuevo servicio remoto ni GPU.

Falla la meta de duplicar utilidad, la meta de 60 % y la condición de no añadir
errores. Pasa el tiempo exigido para la variante principal en ambas corridas,
pero eso no compensa los errores. **No se integra ni se crea versión estable.**
No se abre reserva independiente porque no pasó desarrollo, tal como se registró
antes de medir. [Decisión y costos](g98_closure.json).

Propuesta para una eventual continuación: priorizar el acierto al distinguir
fragmentos con temas parecidos y preguntas que dependen del turno anterior.
Repetir más veces los mismos pares no mejoró la utilidad en este ensayo.
Conservar el mínimo de confianza y exigir nuevas pruebas antes de integrar.
No se inicia otro entrenamiento en esta tanda.

Reproducir la comparación con los archivos locales conservados, eligiendo
una ruta de salida que aún no exista:

```bash
timeout 180s env PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python3 -m experiments.g98_evaluate --output /tmp/g98_reproduccion.json
```

Preregistro `01e49fe`; código educativo `14b0954`; modelos antes de evaluación
`freeze-G98-prototipo` / `0e3183c`. Pesos en `.leobot-data/g98/`, registrados por
huella en los resultados. Motor `leobot/`, base estable y artefactos G-97 intactos.
