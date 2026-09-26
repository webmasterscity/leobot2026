# Auditoría 5.10 — G-57 (kiosco) y `freeze-G-57r`

Encargo de tipo auditor, 2026-09-26.
- Auditor: subagente nuevo de Claude (Opus). Trabajé en una copia aislada de `freeze-G-57r` (`scratchpad/aud57r`, commit `a705c64`, motor `15cfba45…`).
- No modifiqué `leobot/` ni `tests/`, y no hice commit ni tag. Al terminar, la copia seguía limpia y con el mismo motor.
- Mis scripts y salidas están en `scratchpad/aud57r_tmp/`: `paso2.sh`, `paso3.sh`, `paso4.sh`, `muestra30.json`, `muestra_correctas15.json`, `tipos_unidad.py`, `renombrado_g57r.py` y `squad_pool.py`.

## Veredicto: **confirma las cifras**, con objeciones

- **Cifras.** Reproduje exacto todo lo que se me pidió:
  - la base, byte a byte;
  - el banco congelado con `freeze-G-57r`, con las semillas 0 y 1 y con reinicio;
  - las puertas del juez.
- **Orden en git.** Es correcto.
- **Trampas.** No encontré hardcodeo ni filtración del banco.
- **Decisiones.** Todas están declaradas. Hay dos objeciones de fondo:
  - **(a)** El silencio calibrado se conserva contra una regla que la enmienda previa al congelado prometió aplicar «como está escrita».
  - **(b)** La retirada de los títulos quedó a medias: los títulos sueltos siguen siendo respuestas posibles.
- **Qué sería el tag.** Una consolidación, no un avance.
  - El kiosco de `freeze-G-57r` **no contesta ninguna pregunta de contenido**: 0/277. La búsqueda útil solo sale aparte, en `candidate`.
  - La cifra del juez, 140/276, es de **G-57** contestando siempre. De `freeze-G-57r` solo hay conteo automático: 126/277.

## 1. Orden en git — confirmado, con salvedades

| Commit | Hora | Contenido |
|---|---|---|
| `938fac8` | 00:46 | Preregistro y `encargo_redactor.md` |
| `dbdf151` = `freeze-G-57` | 01:04 | Código (`context.py`, cambios en `bot`, `dialogue` y `state_fields`), enmienda, banco de desarrollo A–F y pruebas. Árbol `80d54309…` ✔ |
| `3dd9fd2` | 01:09 | Evaluadores y prueba de privacidad |
| `6e2a42d` | 01:20 | Banco congelado: W1–W6, 72 archivos, más `LEEME.md` y la validación |
| `a364bb1` | 01:27 | Resultados con conteo automático |
| `a705c64` = `freeze-G-57r` | 01:34 | Juez, retiradas y motor nuevo. Árbol `15cfba45…` ✔ |

La cadena es lineal. Después de `938fac8`, el preregistro solo creció: no se borró ninguna línea.

Salvedades:
- **La enmienda entró en el mismo commit que el código.** Son 50 líneas en `dbdf151`. Git prueba que es anterior al banco congelado, no que sea anterior al código. Ya pasó en G-53.
- **Tres evaluadores cambiaron después del banco** (en `a364bb1`):
  - `g57_kiosco.py`: la excepción de `estable-G-15` se registra como tal, y se añadió el renombrado estricto, declarado como diagnóstico posterior;
  - `g57_juez.py`: el mismo registro de la excepción, más la preparación de las ablaciones;
  - `g57_lectura_squad_es.py`: el formato de la clave.

  Ninguno de estos cambios mueve el conteo de G-57 a su favor.
- **Diff `freeze-G-57` → `freeze-G-57r`.** En `leobot/` solo cambia `context.py` (−74, +32 líneas).
  - Quita la forma de las cifras, los términos del título, las secciones, el título antepuesto y el seguimiento (con `_client_turns`).
  - Solo añade una cosa, la declarada: las líneas de pregunta de unas preguntas frecuentes salen del índice.
  - En `tests/` hay dos fallos esperados nuevos, uno por cada pieza retirada.
- **Objeción: la retirada de los títulos está incompleta.** Las unidades de título (`kind == 'heading'`) siguen en el índice, y ahora sin la sección que les daba sentido.
  - Contestando siempre, `freeze-G-57r` da un título suelto en **13 de 603** respuestas. Ejemplos: «hola, cuánto cuesta la entrada?» → «Precios de las entradas»; «¿Hacen descuentos por flota?» → «Flotas y empresas».
  - El conteo automático da una de ellas por correcta.
  - El argumento declarado para las líneas de pregunta («encabeza su respuesta, nunca es la respuesta») vale igual para los títulos.

## 2. Base reproducible — confirmado

- **Educación.** Resultado: `m.json`. 33 787 pares de 1118 dominios; δ para 7039 palabras; δ rara 0,5977; puente de 155 palabras con 960 pares.
  - En la calibración con MFAQ (3885 preguntas) no se admite ninguna celda. La mejor, con al menos 10 casos, acierta el **0,843**, como dice la enmienda (84 %).
  - Tardó 12,8 s y usó 539 MB.
- **Calibración en desarrollo.** Resultado: `b.json`. 391 turnos de A–D, 123 correctos, ninguna celda admitida; la mejor acierta el 0,8125.
  - Tardó 5,1 s y usó 569 MB.
- **SHA-256 de `b.json`**: `3d6ae179f23f6e3bcd58cceb036d09d1dd53d9dc6f09835b7334071e6624971e`. Es **igual** al de `base_freeze_g57r.json`.
- **Desviación no declarada en el preregistro.**
  - El preregistro dice que π se cuenta en los 475 307 pares de MFAQ `train`. Comprobé que el archivo tiene 475 307 pares, 75 099 páginas y 1249 dominios.
  - Pero la educación toma **como mucho 100 pares por dominio**, con un muestreo por reservorio y semilla 57. Así cuenta 33 787 pares (el 7,1 %) de 1118 dominios de enseñanza; otros 85 dominios quedan para calibrar.
  - El tope solo figura en la documentación del script. La intención es razonable (que los sitios con plantilla no dominen), pero hay que declararla.

## 3. Banco congelado con `freeze-G-57r` — confirmado, salvo que el tratamiento no calla «siempre»

| Variante (conteo automático) | Guardado | Reproducido |
|---|---|---|
| Contestando siempre, semilla 0 | 126/277; 579 contestadas; 69,9 % de error | **Igual.** Las 629 respuestas son idénticas a `g57r_contesta_siempre.json` |
| Contestando siempre, semilla 1 | — | 629/629 idénticas: respuesta, estado, celda y candidata |
| Reinicio (contestando siempre) | — | 629/629 idénticas |
| Tratamiento | G-57: 0/277 y 166/166 | **0/277 y 166/166 calladas.** Las respuestas son idénticas a las del tratamiento de G-57; solo cambian 150 candidatas |
| Otro negocio | G-57: 1/413 | Contestando siempre, 1/413 (0/277 en directa y sí/no). El tratamiento no contesta ninguna |
| p95 de `answer` | 0,34 ms (G-57) | 0,14–0,19 ms |

**Salvedad: el tratamiento no calla en todas las preguntas.**
- **El caso.** W2/n1, conversación 1, turno 0: «buenas, quisiera saber donde quedan ubicados». Es una pregunta directa, con la clave «Av. Larco 1245». El motor devuelve el eco «Buenas, quisiera saber donde quedan ubicados.», con el estado `phatic`.
- **La causa.** `_phatic` toma por saludo cualquier turno que cumpla tres condiciones:
  - no lleva «?» ni «¿»;
  - no empieza por una interrogativa aprendida;
  - ninguna de sus palabras está en el índice del documento.
- **Es una desviación no declarada.** El punto 8 del preregistro definía el saludo de otro modo («ninguna palabra con π ≥ el π medio») y la enmienda no lo cambia.
- **El efecto contrario.** 25 de los 50 turnos de charla («Gracias por la info», «Hola, buenos días») reciben «No lo sé: no encontré esa información…». No hay puerta para eso, pero en un kiosco se nota.
- **Cómo lo cuenta el juez.** `auto_label` etiqueta ese eco como `charla` y lo saca del denominador. Por eso G-57 tiene 276 preguntas y `estable-G-15` 277.
  - Un eco que responde a una pregunta debería contar como equivocada.
  - Contado así, el control da 140/277 = 50,5 %, no 50,7 %.
  - `juez_ablaciones.json` sí usa 140/277: los dos archivos no son coherentes entre sí.

## 4. Puertas con el juez — confirmado; en la muestra estoy de acuerdo en 28 de 30

`reunir` da un JSON **idéntico** a `juez_puertas.json`:
- 11 jueces: 8 principales y 3 de ablaciones; 815 ítems más 203 de ablaciones; ningún ítem sin veredicto.
- **Contestando siempre (G-57):** 140/276 (50,7 %). De 578 contestadas: 194 correctas, 43 incompletas, 341 equivocadas y 0 inventadas, es decir, 59,0 % de error. Calladas sin respuesta: 0/166.
- **`estable-G-15`:** 8/277. Contestó 237, con 91,6 % de error y 2 inventadas. Calló 126/166 sin respuesta y tuvo 1 excepción.
- **Tratamiento:** 0/276 y 166/166.

Todo coincide con la sección «Resultado» del preregistro.

**Muestra de 30 veredictos, revisados a mano.** Los elegí al azar con la semilla 20260926: 22 de G-57 y 8 de `estable-G-15`. Leí el texto del negocio, la pregunta, la clave y la respuesta.
- **De acuerdo en 28/30.** No encontré ningún veredicto demasiado duro.
- **Los dos restantes son benévolos:**
  - `i0642` (`estable-G-15`): «in : a partir de las 12 : 00 hs» se dio por **correcta**. Para mí es incompleta.
  - `i0205` (G-57): «Evaluación inicial (…): Paquete de 10 sesiones…; USD 25: USD 170» se dio por **incompleta**. Para mí es equivocada: la tabla tomó la primera fila como nombres de columna, y la respuesta confunde.

**Revisión extra de 15 de las 140 correctas de G-57.**
- 12 son claramente correctas.
- 3 son dudosas y benévolas:
  - `i0059`: la misma fila de tabla mal emparejada;
  - `i0767`: una pregunta de sí o no contestada con un párrafo entero; el «no» hay que deducirlo;
  - `i0042`: el contenido está bien, pero lleva delante un «OK, pero.» raro.

**Conclusión.** El juez es razonable y no cambia ninguna puerta. Pero es benévolo con las líneas citadas tal cual: el encargo del juez lo autoriza («puede traer texto adicional… basta con que deje claro el sí o el no»), y el preregistro no lo dice.
- **El 50,7 % está dentro de ese margen.** Con una lectura más estricta, el control quedaría por debajo del 50 %. No conviene presentar «contestando siempre supera el 50 %» como un hecho firme.
- **El juez no era del todo ciego.** Las respuestas de `estable-G-15` se reconocen, por ejemplo «Procesé 2 segmentos…» o los fragmentos sueltos. Con 140 frente a 8, no cambia nada.

## 5. Hardcodeo y filtraciones (5.7) — no encontré ninguno

**`context.py` de `freeze-G-57r`** (343 líneas).
- No hay listas de palabras.
- Las constantes son de formato:
  - marcas de lista, `#`, `|` y tabulador;
  - fin de oración tras una palabra de 4 o más letras, una cifra o un cierre;
  - línea en mayúsculas o que termina en «:».
- Hay además umbrales y tramos numéricos. Las interrogativas vienen aprendidas (`syntax_model`).
- Los únicos textos fijos son la abstención (`UNKNOWN_TEXT`) y el eco del saludo.
- No hay ramas por el contenido de la pregunta; solo por «¿» y «?».
- La lista de nombres de rol de `_client_turns` («user», «cliente», etc.) era de interfaz, no de contenido, y ya se retiró.

**Resto de `leobot/` desde `estable-G-15`:**
- `bot.py`: la mezcla nueva y 4 campos de estado;
- `state_fields.py`;
- `dialogue.py`: un turno de varias partes devuelve la respuesta a la última pregunta, sin «Procesé N segmentos».

**La base.** Frente a `base_freeze_g55r.json` solo aparecen 4 claves nuevas y no cambia nada más.
- `context_model` guarda solo cuentas:
  - `delta`: palabra → número;
  - `bridge`: palabra → «palabra:probabilidad|…»;
  - `cells` y `cells_mfaq`: cuentas;
  - `admitted`: vacío;
  - `source`: URL, SHA, cuentas y los nombres de carpeta A–D.
- La clave más larga tiene 18 letras y ninguna lleva espacios.
- `context_units`, `context_title` y `context_instructions` están vacíos.

**La calibración** registra `folders = [A, B, C, D]` y 391 turnos. La base se reproduce exacta pasando solo A–D.

**El banco no entra al motor.**
- En `leobot/` no aparece `results_v3`, `kiosco` ni `congelado`.
- Busqué las 842 palabras del banco congelado que no están en el vocabulario de la base: ninguna está en el código del motor.
- Algunas palabras del puente coinciden con el banco («floreria», «mastercard», «cobramos»), pero vienen de MFAQ: la base se reproduce sin el banco.

**Pruebas.**
- `test_g57_kiosco`: 12 pasan y hay 2 fallos esperados.
- `test_follow_up_uses_the_previous_question` **nunca probó el seguimiento**: solo comprueba que la pregunta suelta queda sin respuesta, y no usa `history`. Por eso sigue pasando después de retirar el seguimiento. El nombre engaña.

**Aviso de uso.** `answer` entrega aparte, en `candidate`, la mejor unidad y su precisión. Si un integrador la muestra al cliente, el kiosco contestaría con cerca de un 59 % de error. Hay que documentar que no se muestra.

## 6. Decisiones declaradas

**(a) Silencio calibrado conservado contra su regla. Está declarado y el fondo es defendible, pero tengo una objeción de forma.**
- **Lo que dice la regla.** Se queda si baja (2) a la mitad sin perder más de 10 puntos en (1). Pierde 50,7 puntos, así que habría que retirarlo.
- **Lo que prometió la enmienda.** El punto 7 se escribió antes del congelado, cuando ya se sabía que no se admitiría ninguna celda y que el tratamiento callaría siempre. Aun así escribió: «la regla de retención 5.9 del silencio calibrado se aplica como está escrita». Después de medir, no se aplicó.
- **El argumento de la misión era previsible antes del congelado.** Retirarlo deja 0/166 silencios y 59 % de error. Por eso debió ser una enmienda entonces. Tal como se hizo, es un cambio posterior de un compromiso escrito antes: está declarado, no escondido, pero roza la regla de «no mover la meta».
- **En el fondo estoy de acuerdo.** Entre «contestar siempre, con 59 % de error y 0 % de silencio» y «no contestar nunca», la misión prefiere lo segundo.
- **Pero lo que se conserva no es un silencio calibrado que funcione.** Con la tabla vacía, equivale a decir siempre «No lo sé». Hay que decirlo así en el estado.

**(b) Forma de las cifras retirada sin regla propia. Correcto y declarado.**
- Aporta +1,4 puntos (136 → 140). Queda por debajo de 3 con cualquiera de las reglas preregistradas.
- **Detalle menor.** Llamar «la más estricta» a la regla de los títulos no es exacto: la del puente tiene más condiciones. Aquí no cambia nada.
- **Salvedad.** Retirar títulos y cifras a la vez cuesta −10 en el conteo automático (136 → 126, es decir, −3,6 puntos), por encima de 3.
  - Se aplicó pieza por pieza, como está escrito, y está registrado.
  - `freeze-G-57r` no tiene cifra del juez: no hay que llevar 140/276 al tag.

**(c) Control de renombrado defectuoso. Bien declarado, y la puerta se dejó como no superada. Lo repetí con `freeze-G-57r`:**
- método de G-45: **554/629** (G-57: 552);
- renombrado estricto: **606/629** (G-57: 607).

Hay algo nuevo:
- **Con el método de G-45, el tratamiento da 24/629.** Es la variante que se quiere etiquetar. El control renombra el «No» de la propia abstención del motor, «No lo sé»; con el estricto da 629/629.
- **La puerta se midió sobre «contestando siempre», no sobre el tratamiento**, a diferencia de las puertas 1–3.
- **El defecto es mayor de lo declarado, y ya se conocía.** La auditoría de `estable-G-11` lo señaló («sustituye palabras con mayúscula como El o San»), y aun así se preregistró otra vez. Hay que reparar el control antes de volver a usarlo.

**(d) SQuAD-es con 1570 casos en lugar de 2400. Confirmado que era forzoso.**
- `dev` tiene 10 570 casos:
  - G-47b, G-49 y G-51 usaron 600 cada uno, y quedan 8770;
  - G-52, G-54 y G-55 usaron 2400 cada uno, y quedan **1570**.
- Está declarado en el script y en el preregistro.
- La comparación es pareada sobre los mismos casos (0,2485 frente a 0,2483), así que es válida. Además, `respond` solo cambió en los turnos de varias partes.
- **Aviso.** Ya no quedan casos nuevos de SQuAD-es `dev`. La próxima prueba de «sin retroceso» necesita otra fuente.

**Puertas que pasan sin informar nada.** La 3 (166/166 calladas) y la de «otro negocio» (100 % de silencio) pasan porque el tratamiento no contesta nunca. El preregistro las marca «sí»; debería decir «sí, trivial».

## Otras observaciones

- **El estado no registra G-57.** En `freeze-G-57r`, `LEOBOT_STATE.md` sigue en «Actualizado: 2026-09-25 · estable-G-15», con el «Siguiente paso» antiguo. Hay que actualizarlo antes del tag (paso 7 del ciclo).
- **Lo que no repetí:** la regresión (657/5/0), la latencia fija, el tablero, MFAQ `valid`, la conversación de G-55 y SQuAD-es con `freeze-G-57r`.

**Antes del tag, recomiendo:**
1. Sacar del índice las unidades de título, o declararlas como resto de G-57.
2. Contar como error el eco a una pregunta, y declarar el cambio en la definición de saludo.
3. Declarar el tope de 100 pares por dominio.
4. Escribir en el estado que el kiosco de `freeze-G-57r` no contesta nada de contenido y que `candidate` no se muestra.
5. Citar la cifra propia de `freeze-G-57r` (126/277, conteo automático) y reparar el control de renombrado.

## En palabras fáciles de entender

Se quiso que Leobot atendiera a los clientes de un negocio, como un empleado en un mostrador. Le dan el texto del negocio (precios, horarios, dirección) y él contesta con la frase de ese texto que mejor responde. Si el dato no está, debe decir que no lo sabe.

Revisé el trabajo como alguien de afuera: repetí las pruebas en mi propia copia del programa y comparé.

- **Las cuentas son ciertas.** Me salieron los mismos números, uno por uno, y no hay trampas: el programa no tiene escondidas las respuestas del examen, y el examen se escribió después de congelar el programa.
- **El resultado es malo, y está dicho con honestidad.** Cuando se le obliga a contestar siempre, Leobot acierta más o menos la mitad de las preguntas que tienen respuesta. Pero se equivoca en casi 6 de cada 10 respuestas que da, y nunca reconoce que un dato no está.
- **Por eso se decidió que no conteste nada.** El mecanismo que debía saber cuándo fiarse de su respuesta no encontró ningún caso seguro, así que ante cualquier pregunta de contenido dice «No lo sé». Es seguro, pero hoy no sirve para atender. Esa decisión va en contra de lo que se había escrito antes de empezar; está anunciada y la comparto, pero debió decidirse antes de ver los resultados.
- **Pocas cosas para ordenar.** Si alguien saluda con «gracias», a veces contesta «No lo sé». Una vez repitió la pregunta del cliente como si fuera un saludo. A veces da solo un título suelto, como «Precios de las entradas». Y la prueba de cambiar nombres propios está mal hecha: también cambia palabras corrientes como «No» o «Precio».

**En resumen:** los números son de fiar y no hay trampa, pero el kiosco todavía no funciona. Lo que se puede guardar es una versión ordenada y segura, no un avance.
