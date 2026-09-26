# G-59 — el peso de cada palabra contado contra una respuesta ajena del mismo sitio, y títulos que no responden solos

Fecha: 2026-09-26. Preregistro previo al código. Base: `freeze-G-58r` (árbol `7c8bb1bc`). Prioridad del usuario en `MISION.md` («Prioridad actual»). Es una capacidad general de lectura: elegir bien, entre las líneas de cualquier documento, la que responde.

## Fallo medido (bancos de G-57 y G-58, ya gastados)

**La unidad correcta sí está entre las mejores, pero no primera.** En el banco de G-57, entre las 255 preguntas directas o de sí/no que tienen una unidad con todas las claves, la correcta queda:
- 1.ª en el 49 %;
- entre las 2 primeras en el 62 %;
- entre las 3 primeras en el 71 %;
- entre las 10 primeras en el 88 %.

**Hay 55 casos en que la correcta es 2.ª o 3.ª.** Al revisarlos aparecen dos causas generales:
1. **Las palabras gramaticales deciden empates** («el», «de», «y», «en», «tener», «ser»). Su δ sale inflado: en MFAQ, las preguntas largas tienen respuestas largas, y esas contienen «de» o «el» por su longitud, no por la pregunta. δ = (π − P_A) / (1 − P_A) compara con la tasa de la palabra en *todas* las respuestas, no en respuestas de longitud y estilo parecidos. Ejemplos: «¿cuánto sale el control de la vista?» elige «Hacemos el control visual…» (gana por «de») en vez de «El control dura unos 30 minutos y cuesta $U 950»; «¿atienden los domingos?» elige la presentación del laboratorio (por «atender» y «el») en vez de «Domingos: cerrado».
2. **Un título suelto gana y no responde:** «DÓNDE ESTAMOS», «HORARIO DE ATENCIÓN EN OFICINA», «Club de lectura mensual». La auditoría de G-57r contó 13 casos entre 603 respuestas.

## Cambio (5.8)

**1. δ por contraste con una respuesta ajena** (interruptor de educación; se compara con la base de G-58r).
- δ(q) = (π_propia(q) − π_ajena(q)) / (1 − π_ajena(q)).
  - π_propia: la fracción de preguntas con q cuya respuesta contiene q.
  - π_ajena: la fracción de esas mismas preguntas en que q aparece en **otra respuesta del mismo dominio**, elegida con semilla fija. Es decir, una respuesta de estilo y longitud parecidos que no responde a esa pregunta.
- El puente usa el mismo contraste: δ(q→a) = (P(a en la propia | q) − P(a en la ajena | q)) / (1 − P(a en la ajena | q)). Se conservan el apoyo ≥ 20 dominios, la elevación ≥ 4 y las 12 palabras por q.
- Las palabras raras se tratan igual, en conjunto.
- Si el dominio tiene un solo par, ese par no cuenta para el contraste.
- Todo es conteo. Sin listas: si «de» o «el» pesan poco, es porque aparecen igual en la respuesta ajena.

**2. Un título solo no responde.** Las unidades de tipo título (`heading`) quedan fuera de la búsqueda, igual que las preguntas de unas preguntas frecuentes desde G-57r. Encabezan; no son el dato.

**3. Tablas recontadas con el motor nuevo:**
- MFAQ (celdas de la respuesta plana);
- desarrollo A–D;
- **lo más cercano:** en los bancos de G-57 y de G-58, ya gastados. La etiqueta es el veredicto del juez cuando esa misma unidad fue juzgada (útil = correcta, incompleta o `util`); si no, el conteo automático (todas las claves). Solo cuentas por celda.

**Qué se elimina si funciona:** el δ de G-57 (π frente a P_A de todas las respuestas).

## Medida

Congelado `freeze-G-59`; semilla de su huella.

**A. Banco congelado nuevo** de 24 negocios de 24 sectores distintos de todos los anteriores. 6 redactores nuevos con `isolation: "worktree"`, 4 modelos, el mismo encargo neutral, en git antes de ejecutar.

**B. Juez ciego** (jueces nuevos, Opus), con el encargo de G-58. Califica G-59 y `freeze-G-58r` (la línea base) sobre ese mismo banco, mezclados y sin decir el sistema, más las respuestas que cambian en los controles.

**Umbrales de éxito (banco congelado, juez):**

| Puerta | Umbral |
|---|---|
| 1. Útiles en directa + sí/no | ≥ G-58r **+ 5 puntos** en el mismo banco |
| 2. Inventadas | 0 |
| 2. Respuestas planas, si las hay | error ≤ 2 % |
| 3. Sin respuesta bien llevadas | ≥ 90 % |
| 4. Citas engañosas | ≤ 15 % |
| 5. Eco de datos | 0 |

**6. Controles:**
- sin contraste (base con el δ de G-58r y el motor de G-59);
- sin excluir los títulos;
- tabla barajada;
- otro negocio (útiles ≤ 5 % y «No lo sé» ≥ 80 %);
- reinicio (100 %);
- renombrado estricto (≥ 95 %).

**7. Lectura general, secundaria:**
- MFAQ `valid`, contestando siempre: cobertura no menor que la de G-58r;
- SQuAD-es (los mismos 1570 casos, solo diagnóstico): «la mejor unidad contiene la respuesta» no menor que en G-58r.

**8. Pruebas generales sin retroceso:** conversación 158, regresión completa, latencia 5.6, tablero y sonda.

**Retención 5.9.** Cada cambio se queda si su control muestra que aporta útiles sin subir las engañosas más de 2 puntos.

## Presupuesto

Educación ≤ 5 min. Banco y juez ≤ 1 h. Hasta 16 procesos, con al menos 2 GB de RAM libres.
