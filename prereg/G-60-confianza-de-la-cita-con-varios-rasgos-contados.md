# G-60 — la confianza de la cita contada con varios rasgos aprendidos, citando solo lo que suele servir

Fecha: 2026-09-26. Preregistro previo al código. Base: el motor de `freeze-G-59` con la retención de G-59 aplicada. Prioridad del usuario en `MISION.md` («Prioridad actual»). Guía: el plan 3 de la sesión coordinadora (`/media/leonardo/data/leobotFinal/coordinacion/planes/2026_plan_3.md`), propuestas 1 y 2 y respuesta 4.

Es una capacidad general de autoconocimiento: estimar, con lo aprendido, si la línea encontrada responde de verdad, y mostrar solo lo que suele servir.

## Fallo medido

**1. La celda de confianza separa poco.** La celda actual tiene dos rasgos: δ sin explicar y ventaja sobre la segunda unidad.
- En los bancos gastados (G-57, G-58, G-59 y A–F: 2327 turnos respondidos contestando siempre, 700 con la unidad útil por conteo de claves), su AUC es 0,748.
- En G-59, un orden mejor subió el acierto de las citas (65 % frente a 57 %), pero no cuántas se muestran: 78 útiles frente a 83 de G-58r.

**2. Citar desde 0,5 engaña fuera del banco.** Cifras del coordinador sobre el examen privado del usuario, solo cifras:
- con 0,7: 11/54 útiles y 4 de 15 equivocadas;
- con 0,5: +3 útiles y +8 equivocadas.

**3. Las etiquetas automáticas sirven.** En las 654 citas juzgadas de G-58 y G-59, «contiene todas las claves» coincide con el juez en el 95,3 %: 1 falso positivo y 30 falsos negativos. Es un conteo conservador.

## Cambio (5.8)

**1. Siete rasgos por respuesta candidata.** Todos son de estructura o aprendidos; ninguna lista de palabras.
- `u`: tramo del mayor δ sin explicar (como antes);
- `m`: tramo de la ventaja sobre la segunda unidad (como antes);
- `form`: si la pregunta lleva una interrogativa aprendida (G-42) o es de sí o no. Así el sí o no va por su propia vía de conteo (plan 3, pregunta 2).
- `cls`: la clase de respuesta pedida (G-53) y cuántas veces está en la unidad (0, 1, 2 o más), o «no pide clase»;
- `cov`: qué parte del δ de la pregunta explica la unidad (tramos 0,25 · 0,5 · 0,75 · 1);
- `kind`: tipo de unidad según la maquetación (título, renglón, elemento de lista, fila de tabla, frase);
- `len`: largo de la unidad (tramos 6 · 13 · 26 palabras).

**2. Bayes ingenuo contado.** Cada rasgo aporta su cuenta en útiles y no útiles, con suavizado de Laplace (Zadrozny y Elkan 2002, citado en el plan 3).

**3. Calibración monótona.**
- El puntaje se convierte en utilidad contada con ajuste isotónico, que solo deja subir la utilidad con el puntaje.
- Se ajusta sobre puntajes cruzados: cada turno se puntúa con las cuentas de la otra mitad de los negocios.
- Tramos de al menos 30 casos.
- Hay 2327 casos: el plan 3 desaconseja el ajuste isotónico con menos de 1000.

**4. Punto de operación.**
- Cita avisada solo si la utilidad contada es ≥ 0,7 (plan 3, respuesta 4).
- Respuesta plana: sin cambio (Clopper–Pearson 95 % con error ≤ 2 %; hoy ninguna celda).
- «No lo sé» en el resto.

**5. Retención de G-59 aplicada:**
- sin contraste: la base usa el δ de G-58r;
- los títulos vuelven a la búsqueda, y el rasgo `kind` aprende que un título casi nunca sirve (4 % en desarrollo);
- la clase pedida sigue en el orden.

**Etiquetas y datos.**
- Conteo por claves en los bancos gastados de G-57, G-58 y G-59 y en A–F (desarrollo).
- Un turno cuya acción esperada es abstenerse o derivar cuenta como no útil.
- Solo se guardan cuentas por rasgo y la tabla de calibración; ningún texto.
- Son textos de modelos de lenguaje; se declara.

**Por qué no bastan los mecanismos actuales.** La celda de dos rasgos no ve si la unidad trae la clase pedida, cuánto de la pregunta explica ni qué tipo de línea es. En desarrollo, con validación cruzada por negocios en 3 particiones y citando desde 0,7:

| Confianza | Particiones a, b, c: útiles / citas |
|---|---|
| celda de dos rasgos (≥ 0,7, ≥ 5 casos) | 97/124 · 113/150 · 93/117 |
| Bayes ingenuo con los 7 rasgos, isotónico | 187/245 · 187/240 · 157/198 |

**Qué experimento distingue las hipótesis:** el control «dos rasgos a 0,7», con las mismas etiquetas, el mismo umbral y el mismo motor.

**Qué se elimina si funciona:** la tabla de celdas cercanas de G-58 deja de decidir. Queda solo como control.

## Medida

Congelado `freeze-G-60`; semilla de su huella.

**A. Banco congelado nuevo.**
- 24 negocios de 24 sectores distintos de los 96 anteriores.
- 6 redactores nuevos (herramienta Agent con `isolation: "worktree"`, nunca *fork*), de 4 modelos, con el encargo neutral `results_v3/kiosco/encargo_redactor.md`.
- En git antes de ejecutar.

**B. Juez doble ciego** (plan 3, propuesta 2). Cada respuesta que hay que juzgar la califican:
- un juez Opus y un juez Sonnet 5 nuevos, por separado, con el encargo de G-58;
- si discrepan, un tercero nuevo (Opus), sin ver los dos veredictos, y vale la mayoría.

Se informa el desacuerdo entre los dos primeros.

**Umbrales de éxito (banco congelado, juez doble):**

| Puerta | Umbral |
|---|---|
| 1. Separación: útiles en directa + sí/no | ≥ 1,3 × los del control «dos rasgos a 0,7», y al menos +5; acierto de las citas no menor en más de 3 puntos |
| 2. Punto de operación | citas útiles ≥ 70 % de las citas; engañosas ≤ 5 % |
| 3. Inventadas · respuestas planas | 0 · error ≤ 2 % si las hay |
| 4. Sin respuesta bien llevadas | ≥ 90 % |
| 5. Eco de datos | 0 |

**6. Controles:**
- dos rasgos a 0,7 (puerta 1);
- rasgos barajados: las cuentas de cada rasgo se reasignan al azar entre sus valores. Debe dar menos útiles o menos acierto.
- otro negocio: útiles ≤ 5 % y «No lo sé» ≥ 80 %;
- reinicio: 100 % idénticas;
- renombrado estricto: ≥ 95 % invariantes.

**7. Diagnóstico, sin puerta:**
- G-58r tal como está desplegado (desde 0,5) y G-60 desde 0,5, en el mismo banco y con el mismo juez;
- contestando siempre (conteo automático).

**Lo que se espera y se declara antes de medir:** en desarrollo, frente a G-58r desplegado, G-60 muestra cerca de un 37 % menos de citas útiles y cerca de un 70 % menos de citas que no sirven. Pasar de 0,5 a 0,7 cambia útiles por menos engaños, como pide el plan 3 por el examen privado. La puerta 1 compara la separación con el mismo umbral; la comparación con G-58r desplegado se informa aparte, sin maquillar.

**8. Pruebas generales sin retroceso:**
- conversación 158;
- regresión completa;
- latencia 5.6: p95 de `answer` ≤ 10 ms;
- tablero y sonda;
- MFAQ `valid` contestando siempre y SQuAD-es (los mismos 1570 casos, «la mejor unidad contiene la respuesta»), no menores que G-58r, porque los títulos vuelven a la búsqueda.

**Retención 5.9:** la confianza de siete rasgos se queda si pasa las puertas 1 a 5 y sus controles. Si no, se retira y el kiosco sigue en `estable-G-17`.

## Presupuesto

- Implementación y conteo ≤ 1 h;
- banco ≤ 40 min;
- juez doble ≤ 1 h;
- medidas generales ≤ 30 min.

Hasta 16 procesos, con al menos 2 GB de RAM libres.
