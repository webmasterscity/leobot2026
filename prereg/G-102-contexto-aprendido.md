# G-102 — aprender el contexto de cada palabra

2026-09-28. Excepción neuronal experimental autorizada por el usuario; fuera de
`leobot/`. G-97–G-101 permanecen cerrados. Se restableció el terminal tras el
fallo de `bwrap`; el borrador anterior no llegó a guardarse ni ejecutarse.

## En palabras fáciles de entender

Nuestro modelo suele encontrar frases relacionadas que no contestan lo pedido.
Esta prueba le enseña a comparar cada palabra junto con las palabras vecinas.
Aprenderá con los mismos ejercicios anteriores y preparará el documento al
cargarlo para hacer menos trabajo en cada pregunta. Compararemos esa versión
con otra que mira palabras aisladas y con otra enseñada con preguntas mezcladas.
Solo devolverá citas o se abstendrá. Contaremos también las citas equivocadas:
usar palabras reales no garantiza contestar bien. Es una hipótesis, no una
mejora conseguida. Los mínimos de confianza quedan fijados antes del examen.

## Fuentes, causa y alcance

[Conv-KNRM, WSDM 2018, autores y material](https://boston.lti.cs.cmu.edu/appendices/WSDM2018-ConvKNRM/)
motiva aprender comparaciones de grupos de palabras. No se reclama novedad
científica. G-98 promedia palabras y parejas adyacentes; G-99 compara vectores
de palabras congelados. G-100 continuó esa decisión; G-101 usó Model2Vec estático.
Ya se usaron rivales del mismo documento: eso no es una novedad de G-102.
H1: aprender conjuntamente palabras en contexto y decisión mejora la selección.
El control sin vecinos distingue contexto de mera enseñanza adicional.
Si funciona, sustituiría al selector experimental G-99; no añade piezas al motor.
No pretende resolver relaciones lejanas ni mejorar el historial en este ensayo.

Investigación HF consultada el 28-09-2026: [Sauerkraut15m](https://huggingface.co/VAGOsolutions/SauerkrautLM-Multi-ColBERT-15m)
y [33m](https://huggingface.co/VAGOsolutions/SauerkrautLM-Multi-ColBERT-33m)
incluyen español; sus autores publican 35,34/43,10 en nDCG@10 —medida de
ordenación de documentos—, no porcentajes de respuestas útiles. 15/33 millones
de parámetros, Apache 2.0. Primero mediría 15m por tamaño e idioma.
[NeuML Femto](https://huggingface.co/NeuML/colbert-muvera-femto), aproximadamente
250 mil parámetros, está orientado al inglés. Ninguna ficha demuestra nuestro
límite completo de cinco milisegundos. No se adquieren pesos públicos en G-102.

## Diseño fijado antes de implementar

- Vocabulario y tabla de palabras G-98 como inicio. `Bot.context_terms`, primera
  secuencia de 32 palabras por pregunta y 64 por unidad. Desconocidas conservan
  posición con vector cero y máscara; registrar truncamientos, sin excluirlos.
- Dos convoluciones —combinaciones aprendidas de vecinos— de ancho 3 y 64
  dimensiones, tanh, residuales y máscaras después de cada capa. Proyecciones
  distintas para pregunta/documento inicializadas con G-98 y normalización L2.
  Documentos preparados al cargar; ninguna respuesta futura precalculada.
- Comparación por palabra mediante mejor coincidencia; media, mínimo,
  desviación, cuartiles y máximo, junto a las 13 variables léxicas de G-99.
  Decisión de 48 unidades, tanh, salida escalar, opción vacía de puntaje cero.
  Pérdida G-99: selección más 0,25 de binaria. Toda la tabla y capas aprenden.
  Variables léxicas estandarizadas con enseñanza; coincidencias ya acotadas.
- Tres variantes: `context` principal; `width1` de ancho 1 sin vecinos;
  `shuffled`, arquitectura principal con preguntas permutadas por grupo como
  G-99. Ancho 1 tiene menos pesos: informar ambos tamaños. Mismos ejemplos,
  seis épocas, semilla 1, lote 16, AdamW 0,001, decaimiento 0,001.
  Usar estado final de sexta época, sin elección de pesos por evaluación.
- Mismas filas, unidades, etiquetas y particiones G-98: 6000 SQAC humanos y
  1737 ejercicios sintéticos de negocios; 1798 de comprobación educativa;
  455 propuestas de calibración en negocios separados. Verificar huellas.
  Sin nuevos ejemplos hechos para errores del examen ni listas semánticas.
- Confianza isotónica —acierto observado por nivel de puntaje— ajustada solo
  con calibración; mínimos 0,4 y 0,9 fijos, principal `context_90`, puntaje >0.
  Medir selección sin puerta y respuestas reales, sin equiparar semejanza a certeza.

## Evaluación y presupuesto

- Evaluador G-97 intacto, muestra gastada de 157 turnos/102 contestables; no
  reserva. Referencias estable, G-98 y G-99 lexical. Panadería exacta aparte.
- Respaldo solo de abstenciones; conserva errores anteriores: informar todos
  los heredados y nuevos. Techo 90/102; este ensayo no certifica perfección.
- Paso intermedio: ≥37/102 útiles, cero errores nuevos, selección cruda >22/61
  (candidata estable). Meta ≥62/102. Dos procesos: p95 y máximo completo y
  condicional <5 ms, una hebra; mediana y número de consultas >5 ms también.
- Si pasa: nueva reserva independiente preregistrada antes de generalidad.
  Si falla: cerrar y conservar negativos; no ampliar búsqueda ni cambiar mínimos.
- Desactivación, exportación NumPy, recarga exacta, cambio/vaciado documental,
  retirada de evidencia, huellas de motor/base y pruebas rápidas/focales.
  Igual información y control confundido presentes; memoria sola es estable.
  Sin reserva nueva ni renombrado estructural en un ensayo que falle desarrollo.
- Preparación, enseñanza y calibración ≤1200 s CPU/1800 s pared; evaluación y
  reinicios juntos ≤300 s CPU/500 s pared; memoria máxima 3 GiB por proceso,
  una hebra y un trabajo pesado. Timeout cierra incompleto, sin elegir pesos
  parciales. Separar costos nuevos/reutilizados, preparación y arranque frío.

## Implementación y órdenes

1. Commit del preregistro; pruebas rápidas. `experiments/test_g102_context.py`:
   equivalencia NumPy/enseñanza, máscara, vacíos y efecto del orden frente a ancho1.
2. `g102_context.py`: preparación/decisión; `g102_training.py`: enseñanza y
   calibración; `g102_evaluate.py`: adaptar construcción sobre evaluador intacto.
3. Pruebas focales; commit y `freeze-G102-prototipo` antes de enseñar.
4. `timeout 1800s env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
   PYTHONHASHSEED=0 python3 -m experiments.g102_training`; congelar pesos por SHA.
5. `timeout 250s env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
   PYTHONHASHSEED=0 python3 -m experiments.g102_evaluate
   --output results_v3/g102_common.json`; repetir con hashseed1 a otro archivo.
6. Informar resultados, costo, controles y fuentes en `results_v3/g102_resumen.md`
   y `LEOBOT_STATE.md`; artefactos `.leobot-data/g102/`. Sin promoción automática.
