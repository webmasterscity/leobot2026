# Auditoría independiente del ciclo G-62 (regla 5.10, tipo auditor)

Fecha: 2026-09-26. Auditor: Claude (subagente nuevo, copia de trabajo aislada en `319b18f`, motor `freeze-G-62` = `8839d77d33f5f4198c5d7e6d6f835a23efe5bd50`). No se tocó `leobot/`, ni las pruebas, ni la rama principal. Todo lo producido está en `aud62/`, dentro de esta carpeta temporal.

## Veredicto

**Se confirma el resultado declarado.** Todas las cifras de las puertas y de los controles se reproducen exactamente, las respuestas salen idénticas a las guardadas y no hay hardcodeo ni filtración del banco. Hay seis objeciones. Ninguna cambia el veredicto de las puertas preregistradas, pero dos cambian cómo debe leerse el resultado (1 y 2).

## Qué se confirmó

**Orden en git**
- El preregistro `01d10af` (03:52:42) va antes del commit del motor `cdca450` = `freeze-G-62` (03:53:39).
- El banco `a90ad03` (04:11:12) entró en git 18 minutos después de la congelación. La evaluación empezó a las 04:11:14, dos segundos después del commit del banco: el archivo temporal `/tmp/g62_9h8glxts/barajada.json` es de las 04:11:14. Los resultados se escribieron entre 04:11:17 y 04:12:52, y el juez trabajó entre 04:13 y 04:17.
- Los encargos del redactor (`encargo_redactor.md`, sin cambios desde G-57) y del juez (`juez58_encargo.md`, sin cambios desde G-58) no se tocaron en el ciclo.

**Reproducibilidad**
- La base reconstruida con las órdenes dadas **no es idéntica byte a byte**: su huella SHA-256 (código que identifica un archivo) es `589facc1…`, y la declarada es `6c3c11b0…` (objeción 3). Sí es idéntica en todo lo que el motor usa: `cells`, `closest`, `closest_cells`, `confidence`, `bridge`, `delta`, `rare_delta` y `admitted` coinciden. Solo difieren `cells_mfaq` y `source`, que el motor no lee: se comprobó con `grep` en `leobot/`.
- La evaluación completa (11 sistemas × 647 turnos) da respuestas, estados, celdas y veredictos automáticos **idénticos** a los guardados en tres casos:
  - con la base declarada y `PYTHONHASHSEED=0`;
  - con la base reconstruida por el auditor y `PYTHONHASHSEED=0`;
  - tratamiento y G-58r con `PYTHONHASHSEED=1`.
- Pruebas generales:
  - MFAQ `valid` contestando siempre: **57,24 %** (0,5724), igual a lo declarado;
  - regresión completa: **667 pruebas, 6 fallos esperados, 0 fallos**.

**Puertas del juez, recalculadas desde los veredictos guardados:** coinciden todas.

| | Declarado | Auditoría |
|---|---|---|
| Útiles directa + sí/no | 99/276 frente a 69/276 | 99/276 frente a 69/276 (+10,9 puntos) |
| Citas engañosas | 5/199 (2,5 %) frente a 2/149 (1,3 %) | igual |
| Inventadas · planas | 0 · 0 | 0 · 0 |
| Sin respuesta bien llevadas | 175/176 (99,4 %) | igual |
| Eco de datos | 0 | 0 |
| Controles | todo encabezado 103, sin herencia 86, sin pregunta en línea 93, barajados 13 (26,4 % útiles), otro negocio 1/276 y 580/647 «No lo sé» (89,6 %) | igual |
| Reinicio | 647/647 | 647/647 respuestas iguales |
| Renombrado estricto | 640/647 | 640/647 respuestas iguales tras deshacer el renombrado |
| Contestando siempre | 134 frente a 126 | igual |
| p95 de `answer` en el banco | 0,26 ms | 0,258 ms |

- Hay 0 ítems sin juicio en los sistemas juzgados.
- Otras cifras concuerdan con sus archivos: SQuAD-es, unidad con la respuesta 0,8013 y F1 0,2485; latencia intercalada con `estable-G-17`, cambios de p95 entre −7,6 % y +1,2 %, 220 MB.
- **Solidez de la ganancia frente a G-58r.** En pares, G-62 gana en 36 turnos y pierde en 6; la prueba exacta de McNemar (prueba de pares) da p < 0,0001. Remuestreando por negocio, el intervalo al 95 % de la diferencia va de +5,9 a +16,4 puntos. 13 negocios ganan, 11 quedan igual y ninguno pierde.

**Revisión a mano de 30 veredictos del juez** (12 solo del tratamiento, 8 solo de G-58r y 10 compartidos, sorteados con semilla 62): coincido en **29 de 30**.
- El dudoso es `i0041` (G-58r). A «¿tienen marcos redondos u ovalados?» se cita «R: Sí, tenemos marcos especiales tipo caja…». El juez puso «honesta»; ese «Sí» inicial podría hacer creer algo falso, así que yo lo inclinaría a «engañosa». No afecta a las puertas.
- `i0212` («útil» para una cuenta de 3 paquetes cuando se cita el precio de uno) es generoso, pero cabe en la regla del encargo («o su parte principal»).
- Los 8 jueces escribieron un veredicto y un motivo por ítem, sin reglas automáticas: se revisaron sus guiones en `jueces62/`. El juez 6 usó una lista por posición; en los 3 ítems suyos de la muestra, veredicto y motivo corresponden al ítem.

**Hardcodeo y filtraciones (5.7)**
- `git diff freeze-G-61 freeze-G-62 -- leobot`: 15 líneas en `_layout_units`. Deciden qué encabezado se hereda según la tipografía: `#` de markdown, línea toda en mayúsculas, dos puntos al final y línea en blanco. No hay listas de palabras ni ramas por negocio, sector o pregunta.
- `git diff freeze-G-58r freeze-G-62 -- leobot`: solo `context.py`, con los cambios de G-59 a G-62. Los interrogativos, las clases de palabras y las clases de respuesta son tablas aprendidas (`syntax.py:319`, `reading_model`). La confianza es un Bayes ingenuo (clasificador que suma pruebas contadas) sobre cuentas guardadas en la base.
- El motor no lee bancos, evaluadores ni resultados: no hay referencias a `results_v3`, `experiments`, `congelado` ni `juez` en `leobot/`, y `context.py` no abre archivos.
- Las cuentas de la confianza **no usan el banco de G-62**. La base declarada lista 6 bancos gastados, y la reconstruida sin `congelado_g62` tiene la tabla `confidence` idéntica.

## Objeciones

**1. La puerta de MFAQ se eligió mirando el mismo examen.** Gravedad: media.
- Las cuatro variantes de alcance del preregistro se midieron sobre MFAQ `valid`, el mismo archivo de la puerta 7. El guion `mfaq_abl.py` lee `/tmp/mfaq_es_valid.jsonl`, con la huella `9d1c868e…`.
- Los registros `mfaq62_all/_block/_caps/_questions/c.log` son de las 03:45–03:52, antes del commit del preregistro. La variante elegida da justo 0,5724, el umbral.
- El preregistro lo llama «en desarrollo» y «declarado antes de medir». En realidad es el valor ya medido en el conjunto de la puerta.
- Consecuencia: «MFAQ no menor» no es evidencia independiente, y va contra la regla 4 de `CLAUDE.md` (no medir una y otra vez el mismo examen).
- Además, la diferencia que tumbó G-61 y aprueba G-62 (0,34 puntos) son unas **9 preguntas de 2687**: está dentro del ruido.

**2. El cambio propio de G-62 no mejora el kiosco frente a G-61.** Gravedad: media, de interpretación.
- Los +10,9 puntos frente a G-58r son del conjunto de G-59 a G-62: «sin herencia» ya da 86 frente a 69.
- Frente a su antecesor directo, el alcance de G-61 (`todo_encabezado`), G-62 da **99 frente a 103**: gana 2 turnos y pierde 6 (p ≈ 0,29, sin diferencia clara).
- El preregistro lo dice, y la regla de retención 5.9 preregistrada compara con «sin herencia», no con G-61. Por eso G-62 pasa en regla.
- Lo único que respalda preferir G-62 a G-61 es la objeción 1: 9 preguntas de MFAQ en el conjunto que se usó para elegir.

**3. La receta de la base no la reproduce byte a byte.** Gravedad: baja.
- Con las órdenes dadas sale `589facc1…`, no `6c3c11b0…`.
- La base declarada trae `source.closest` (un paso de G-58, `g58_calibrar_cercano`, con dos bancos) y otro `cells_mfaq`. Es decir, se hizo desde una base intermedia distinta de la que indican las órdenes.
- No afecta a ninguna respuesta: los 11 sistemas dan lo mismo con ambas bases. Aun así, conviene registrar la cadena exacta.

**4. El preregistro llegó después del diseño.** Gravedad: baja.
- El orden en git se cumple, pero por 57 segundos.
- La variante final ya estaba escrita y medida en desarrollo antes del commit del preregistro: registros de 03:45 a 03:52 y una copia previa del motor en `context_g62_marked.py`, de las 03:49.
- El preregistro recoge esas cifras. Los umbrales son los mismos de G-61, así que no se movió la meta.
- Lo decisivo sí está protegido: el banco se escribió después de congelar.

**5. «Sin respuesta bien llevadas: 99,4 %» mide «no inventó», no «siguió las instrucciones».** Gravedad: baja. Es una definición heredada de G-57 y G-58, no de este ciclo.
- En 50 de los 58 turnos donde el negocio pide derivar a una persona, Leobot dice «No lo sé: no encontré esa información…» sin derivar, y cuentan como bien llevados.
- Además, 22 de 44 saludos o agradecimientos reciben «No lo sé», y 3 reciben una cita. Esto no lo declara el resultado, solo el eco breve.

**6. Menores.**
- La respuesta del kiosco tarda el doble que en G-58r: p95 de 0,125 a 0,258 ms. Está muy por debajo del presupuesto de 10 ms, pero la prueba fija de latencia 5.6 no mide `answer`.
- Con el texto de otro negocio, 20 de 36 citas engañan. Está declarado y es la objeción 2 de G-58r, que sigue abierta.
- La regla nueva es una regla de maquetación escrita a mano, no aprendida. No depende de palabras ni de negocios, así que no la considero hardcodeo según 5.7, pero está en la frontera del punto 1 de `CLAUDE.md`.
- El banco lo escribieron modelos de lenguaje con títulos en mayúsculas muy regulares, y la regla depende de esa tipografía. Falta comprobar que se sostiene con textos de negocios escritos por personas.

**Controles:** no falta ninguno de los preregistrados y todos se aplicaron bien. No aplican bot fresco, contraevidencia ni señal confundida: el ciclo mide lectura de un documento, no aprendizaje de una hipótesis.
- Falta un control útil: la confianza contada con el alcance de G-61 para `todo_encabezado`. Ahora ese control usa la tabla contada con el alcance de G-62, lo que, si acaso, lo perjudica, y aun así gana por 4.

## Órdenes usadas

Todas desde la raíz de la copia `.claude/worktrees/agent-a280fe3a852d3c3a2` en `319b18f` (`HEAD:leobot` = `8839d77d…`), con `PYTHONHASHSEED=0` salvo donde se indica. `S` es esta carpeta y `A=$S/aud62`.

```
# 1. Base (19 s + 10 s + 12 s; RAM pico 570 MB)
python3 -m experiments.g57_educar_kiosco $S/base_freeze_g55r.json $A/m.json --sin-contraste
python3 -m experiments.g57_calibrar_kiosco $A/m.json $A/c.json results_v3/kiosco/desarrollo/{A,B,C,D}
CONFIANZA_BANCOS=results_v3/kiosco/congelado,results_v3/kiosco/congelado_g58,results_v3/kiosco/congelado_g59,results_v3/kiosco/congelado_g60,results_v3/kiosco/congelado_g61,results_v3/kiosco/desarrollo CONFIANZA_CITA=0.4 python3 -m experiments.g60_calibrar_confianza $A/c.json $A/b.json
sha256sum $A/b.json $S/base_g62.json          # 589facc1… frente a 6c3c11b0…
python3 $A/diffjson.py $A/b.json $S/base_g62.json ; python3 $A/cmpcm.py …   # solo cells_mfaq y source

# 2. Evaluación (1 min 56 s; RAM pico 985 MB por proceso)
G62_WORKERS=3 G62_HUELLA=8839d77d33f5f4198c5d7e6d6f835a23efe5bd50 python3 -m experiments.g62_evaluar $S/base_g62.json $S/base_freeze_g58.json $S/wt_g58r $A/eval0 results_v3/kiosco/congelado_g62/Q{1..6}
(misma orden con $A/b.json → $A/eval_mine)
PYTHONPATH=<copia> PYTHONHASHSEED=1 python3 experiments/g57_kiosco.py $S/base_g62.json $A/eval_hs1/tratamiento.json …Q1…Q6 --respuestas
PYTHONPATH=$S/wt_g58r PYTHONHASHSEED=1 python3 experiments/g57_kiosco.py $S/base_freeze_g58.json $A/eval_hs1/g58r.json …Q1…Q6 --respuestas
python3 $A/cmprows.py <dir> results_v3/kiosco/evaluacion_g62 <sistemas>   # 0 filas distintas en todo

# 3. Puertas del juez
JUECES_SISTEMAS=tratamiento,g58r,todo_encabezado,sin_herencia,sin_preguntas_en_linea,rasgos_barajados,otro_negocio JUECES_OTROS=renombrado_estricto JUECES_SEMILLA=8839d77d33f5f4198c5d7e6d6f835a23efe5bd50 python3 -m experiments.g58_juez reunir results_v3/kiosco/evaluacion_g62 results_v3/kiosco/evaluacion_g62/juez $A/p.json
python3 $A/cifras.py ; PYTHONPATH=<copia> python3 $A/renombre.py ; python3 $A/muestra.py > $A/muestra.txt

# 4. Pruebas generales
python3 -m experiments.g57_mfaq_valid $A/b.json $A/mfaq.json      # contesta_siempre 0,5724
python3 -m experiments.regression_batches                          # 667 / 6 esperados / 0 fallos, 110 s

# Revisión de código y orden
git diff freeze-G-61 freeze-G-62 -- leobot ; git diff freeze-G-58r freeze-G-62 -- leobot
grep -rn "results_v3\|experiments\|congelado\|kiosco\|juez" leobot/
git log --format='%h %ad %s' --date=iso freeze-G-61..HEAD ; stat de los archivos de $S/eval62, $S/jueces62 y $S/k62
```

Durante toda la auditoría quedaron libres al menos 5,7 GB de RAM.

## En palabras fáciles de entender

Revisé por mi cuenta el último cambio de Leobot, el que decide qué título de un documento corresponde a cada renglón. Repetí todas las pruebas y los números salieron exactamente iguales a los que se habían anotado, también cambiando el orden interno de la computadora. El examen de 24 negocios se escribió después de congelar el programa, el programa no lo pudo ver, y los jueces calificaron cada respuesta una por una. También revisé yo mismo 30 de sus notas y estoy de acuerdo con 29. Con esto, Leobot da una respuesta útil en 99 de 276 preguntas, frente a 69 de la versión estable anterior, sin inventar nada. Esa mejora es real, pero viene de varios cambios juntos. Este último, por sí solo, no mejora al anterior en el kiosco: da 99 frente a 103. Se prefirió porque no empeora otra prueba de preguntas frecuentes, y esa diferencia es de unas 9 preguntas entre 2687, en la misma prueba que se usó para escogerlo. Además, cuando un negocio pide pasar al cliente con una persona, Leobot casi siempre dice solo «No lo sé», y eso se cuenta como bien hecho aunque no siga la instrucción.
