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
