# Diagnóstico 1 de la sesión de nube (2026-09-28): dónde está el techo del kiosco

Motor sin cambios (`11a1ef58`, igual a `estable-G-19`). Solo experimentos y datos fuera de `leobot/`.
Fuentes alcanzables: AnCora, SQuAD-es, MCR/WordNet. MFAQ, MLQA y COSER no. La línea base **B0** (`experiments/nube_educar.py`)
sustituye MFAQ por SQuAD-es; **sus cifras no son comparables con las históricas** (35,9 % con juez). Bancos ya gastados: sirven para
elegir dirección, no para afirmar mejora.

## Línea base B0 (conteo automático, bancos G-62 a G-64, 1 851 turnos)
directas + sí/no útiles 228/816 (27,9 %). Nunca contesta «a secas»; 797 abstenciones indebidas. Sin respuesta: 488/488 sin inventar.

## Recuperación de la unidad correcta (turnos directa + sí/no con alguna unidad que contiene las claves)
| variante | desarrollo top1 (n=264) | validación top1 (n=741 o 1009) |
|---|---|---|
| BM25 puro (sin educación) | 0,500 | 0,494–0,496 |
| mezcla actual (δ aprendido + puente + clase), B0 | 0,587 | 0,559 |
| + prefijos comunes (≥3 letras, ≥0,5) | 0,614 | 0,580 |
| WordNet (sinónimos), secciones jerárquicas, proximidad, bigramas, sin encabezados | sin ganancia | sin ganancia |
top3 ≈ 0,75–0,78; top5 ≈ 0,82–0,85.

## Seguimientos con historial (n=65 desarrollo, 198 validación)
Arrastrar los términos del turno anterior y reforzar la sección de la unidad previa: top1 0,455→0,520 (validación). **Aplicado siempre daña
las preguntas independientes** (directas + sí/no: 0,580→0,521): hace falta una compuerta aprendida.

## Distinguir «está en el texto» de «no está» (validación cruzada por negocio, 9 bancos)
AUC de la confianza actual 0,78. Un modelo por candidata con ~20 rasgos generales: regresión logística 0,815, árboles potenciados 0,836.
Útiles entre las respondibles al mismo nivel de citas sobre lo no respondible: 10 % → 0,235 (actual), 0,291 (LR), 0,324 (GBM); 20 % → 0,337 / 0,405 / 0,425.
Reordenar entre las ocho primeras con ese modelo: top1 0,554→0,585 (LR).

## Control ya guardado (G-64)
Contestar siempre: 134/266 útiles (50,4 %) pero inventa en 158/158 preguntas sin dato. El cuello es la discriminación, no solo el orden.

## Estructura que `answer()` ignora
Historial, instrucciones del negocio y cuentas: seguimiento + instrucción + combinada ≈ 28 % de los turnos y casi cero de aciertos.
