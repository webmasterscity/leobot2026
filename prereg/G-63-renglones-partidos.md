# G-63 — leer una oración partida en varios renglones como una sola

Fecha: 2026-09-26. Preregistro previo al commit del motor. Base: `estable-G-18` (`freeze-G-62`). Prioridad del usuario en `MISION.md` («Prioridad actual»).

Es una capacidad general de lectura: el texto que se pega desde una página web, un PDF o un correo suele llegar con la oración partida en renglones.

## Fallo medido

**1. Examen privado del usuario sobre `estable-G-18`.** Cifras de la sesión coordinadora; el examen no se leyó. Dos citas salen cortadas a media frase («…mayores a», «…regular los»): el texto trae oraciones partidas en renglones, y cada renglón se toma como una unidad.

**2. En los bancos de desarrollo esta forma casi no aparece:** 7 casos en 168 negocios, porque los modelos de lenguaje no parten las líneas. Para medirla se parten mecánicamente los textos gastados a 70 columnas:

| Texto (bancos de G-59 a G-62, `estable-G-18` tal cual) | Útiles en directa + sí/no (de 1116) | Citas útiles · no útiles |
|---|---|---|
| tal cual | 403 | 501 · 217 |
| partido a 70 columnas | 268 | 324 · 334 |
| **partido a 70, uniendo renglones** | **366** | 454 · 244 |
| tal cual, uniendo renglones | 403 (idéntico) | 501 · 217 |

Contestando siempre (simulación cruzada, de 538): 291 tal cual, 202 partido, 268 partido y uniendo.

## Cambio (5.8)

**Unir renglones partidos** (interruptor `join_wrapped`, en `_layout_units`). Es una regla de maquetación, no de palabras. Un renglón continúa en el siguiente cuando se cumplen estas cuatro condiciones:
- el renglón no parece un título (más de 8 palabras o sin la forma de título);
- termina sin puntuación de cierre (su último carácter es letra o cifra);
- el siguiente empieza en minúscula o con una cifra;
- ninguno de los dos es una fila de tabla, y el siguiente no es un elemento de lista.

Los dos renglones se unen con un espacio.

**Sin cambio:** la base es la de `estable-G-18` (`base_g62.json`, sha256 `6c3c11b0…`), con la misma confianza contada y los mismos conteos.

**Por qué los mecanismos actuales no bastan:** cada renglón es una unidad, así que una oración partida da dos unidades incompletas.

**Qué experimento distingue:** el mismo banco nuevo en dos presentaciones, tal cual y partido a 70 columnas, con el control «sin unir».

**Qué se elimina si funciona:** nada.

## Medida

Congelado `freeze-G-63`; semilla de su huella.

**A. Banco congelado nuevo.**
- 24 negocios de 24 sectores distintos de los 168 anteriores.
- 6 redactores nuevos (herramienta Agent con `isolation: "worktree"`, nunca *fork*), de 4 modelos, con el encargo neutral de siempre. No se les pide partir renglones.
- En git antes de ejecutar.

**Presentación partida:** el evaluador parte `negocio.txt` a 70 columnas, en palabras, antes de cargarlo, igual para todos los sistemas. Es una transformación mecánica declarada. Las instrucciones y las preguntas no se tocan.

**B. Juez ciego** (8 jueces nuevos, Opus, encargo de G-58). Califica las respuestas de G-63 y de `estable-G-18` en las dos presentaciones, mezcladas, y las que cambian en los controles. El juez ve el `negocio.txt` original.

**Umbrales de éxito (banco congelado, juez):**

| Puerta | Umbral |
|---|---|
| 1. Útiles en directa + sí/no, texto partido | ≥ `estable-G-18` partido + 5 puntos |
| 2. Texto tal cual | respuestas idénticas a `estable-G-18` en ≥ 98 % de los turnos, y útiles no menores |
| 3. Citas engañosas, en cada presentación | ≤ 15 % y no más de 2 puntos por encima de `estable-G-18` |
| 4. Inventadas · planas | 0 · error ≤ 2 % si las hay |
| 5. Sin respuesta bien llevadas, en cada presentación | ≥ 90 % |
| 6. Eco de datos | 0 |

**7. Controles:**
- sin unir, texto partido (debe dar lo de `estable-G-18` partido);
- reinicio, texto partido: 100 %;
- renombrado estricto, texto partido: ≥ 95 %;
- otro negocio: útiles ≤ 5 % y «No lo sé» ≥ 80 %.

**8. Pruebas generales sin retroceso, frente a `estable-G-18`:**
- **MFAQ `valid` con contención normalizada** en los espacios, para los dos sistemas: no menor. Es una medida nueva y se declara aquí antes de medir, por dos razones:
  - el evaluador original compara la unidad con la respuesta carácter a carácter, y una unidad unida lleva un espacio donde el original tenía un salto de línea. En desarrollo, eso sola baja la cifra de 57,24 % a 55,97 %, mientras con espacios normalizados sube a 57,31 %.
  - la cifra con el evaluador original también se informa.
  - MFAQ `valid` ya se usó para elegir en G-62, así que es un diagnóstico, no una prueba limpia.
- SQuAD-es, unidad con la respuesta: ≥ 0,8013;
- conversación 158;
- regresión completa sin fallos;
- latencia 5.6;
- tablero y sonda sin cambio.

**Retención 5.9:** la unión de renglones se queda si pasan las puertas 1 a 6 y los controles.

**Tag estable:** si pasa, con auditoría 5.10.

## Presupuesto

Implementación ≤ 20 min; banco ≤ 40 min; juez ≤ 1 h; medidas generales ≤ 40 min; auditoría ≤ 1 h. Hasta 16 procesos, con al menos 2 GB de RAM libres.

## Resultado preliminar e incompleto (2026-09-26): la medida no se pudo terminar (superado por el resultado final, abajo)

**El límite semanal de la API cortó a los redactores**; se reinicia el 30 de septiembre.
- El banco quedó en 15 de 24 negocios y 396 turnos. `results_v3/kiosco/congelado_g63/LEEME.md` dice qué se incluyó.
- No hubo juez ciego ni auditoría. Las cifras siguientes son de conteo automático y **no deciden ninguna puerta**.

| Presentación | G-63 | `estable-G-18` | Sin unir (G-63) |
|---|---|---|---|
| Tal cual: útiles en directa + sí/no | 34/180 | 34/180 | — |
| Tal cual: respuestas idénticas | 396/396 | — | — |
| Partido a 70: útiles en directa + sí/no | **32/180** | 27/180 | 27/180 |
| Partido a 70: citas útiles · no útiles | 40 · 36 | 36 · 44 | 36 · 44 |

**Controles:**
- reinicio con texto partido: 396/396;
- otro negocio: 0 útiles y 352/396 «No lo sé».

**Pruebas generales (`freeze-G-63`):**
- MFAQ normalizado 57,31 % frente a 57,24 %; con el evaluador original, 55,97 % (el artefacto declarado);
- SQuAD-es 0,8013;
- conversación 158;
- regresión 668/6/0.

En el banco parcial, la ventaja con texto partido es de +2,8 puntos (automático), lejos de los +8,8 del desarrollo. Con 180 preguntas no se puede concluir nada.

**Estado:** el motor de G-63 queda en la rama `G-63`; main vuelve al motor de `estable-G-18`. Para retomar:
1. redactar los 9 negocios que faltan (R4, R5 y el cuarto de R6), con el mismo encargo y los mismos sectores;
2. pasar el juez;
3. decidir las puertas;
4. auditoría 5.10 si pasa.

## Resultado final (2026-09-26, banco completo de 24 negocios y 619 turnos; juez ciego de 8 jueces nuevos, Opus)

El banco se completó con 9 negocios de redactores nuevos, en git antes de ejecutar (`results_v3/kiosco/congelado_g63/LEEME.md`). Desvío declarado: R4 lo escribió Sonnet 5 en lugar de Fable 5.1, así que el banco tiene 3 modelos y no 4. Cinco jueces se cortaron por el límite de sesión; uno ya había dejado su archivo completo y los otros cuatro se relanzaron con el mismo encargo.

| Puerta | Umbral | G-63 | `estable-G-18` | ¿Pasa? |
|---|---|---|---|---|
| 1. Útiles en directa + sí/no, texto partido | ≥ `estable-G-18` + 5 puntos | **95/274 (34,7 %)** | 83/274 (30,3 %) | **no (+4,4)** |
| 2. Texto tal cual | idénticas ≥ 98 %, útiles no menores | 619/619 idénticas; 102/274 | 102/274 | sí |
| 3. Citas engañosas | ≤ 15 % y ≤ +2 puntos | partido 3,8 %; tal cual 2,7 % | 3,3 %; 2,7 % | sí |
| 4. Inventadas · planas | 0 · — | 0 · ninguna | 0 | sí |
| 5. Sin respuesta bien llevadas | ≥ 90 % | 99,4 % en las dos | 98,7 %; 99,4 % | sí |
| 6. Eco de datos | 0 | 0 | 0 | sí |

**Controles:**
- sin unir, texto partido: respuestas idénticas a `estable-G-18` partido en 619/619;
- reinicio, texto partido: 619/619;
- otro negocio: 0 útiles; 545/619 «No lo sé» (88,0 %); 6 respuestas que los jueces marcan como inventadas, que son texto literal del documento de otro negocio, como en G-62;
- renombrado estricto, texto partido: 552/619 turnos con la misma decisión y la misma línea (89,2 %, conteo automático), por debajo del 95 %. Posible causa, no comprobada: al renombrar cambia el largo de las palabras y el texto se parte en otros sitios.

**Decisión (regla 5.9 y la de retención de este preregistro):** la puerta 1 falla por 0,6 puntos, así que **la unión de renglones no entra**. La meta no se mueve después de medir. Main vuelve al motor de `estable-G-18`; el motor de G-63 queda en la rama `G-63` y en `freeze-G-63`. Sin auditoría 5.10, porque no hay tag.

**Lo que sí queda como evidencia:** con texto partido, unir renglones gana 12 útiles sin subir las engañosas ni inventar, y con texto tal cual no cambia ninguna respuesta. Es una ganancia real pero menor que la pedida: en desarrollo fueron +8,8 puntos; en el banco nuevo, +4,4.
