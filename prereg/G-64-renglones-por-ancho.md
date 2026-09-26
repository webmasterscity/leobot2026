# G-64 — unir renglones partidos usando el ancho del propio documento

Fecha: 2026-09-26. Preregistro escrito **antes** de medir en desarrollo y antes de tocar el motor. Base: `freeze-G-63` (la unión de renglones de G-63, que no entró). Pedido del usuario: subir la ganancia de G-63 con texto partido sin trampas.

## Fallo medido

G-63 unía un renglón con el siguiente solo si el siguiente empezaba en minúscula o con una cifra y el primero terminaba en letra o cifra. En su banco congelado, con texto partido, dio +4,4 puntos frente a `estable-G-18` (pedía +5).

En desarrollo (bancos de G-59 a G-62, partidos a 70 columnas), con texto partido y unido acierta 366 de 1116, y con el texto original 403; esos 37 útiles son lo que la unión todavía no recupera. **No se mira el banco de G-63**: está gastado.

## Variantes candidatas (declaradas antes de medir)

Todas son reglas de forma del texto, sin listas de palabras. Ninguna ajusta números con el banco.

- **V0 (G-63):** la regla de G-63, tal cual.
- **V1 (coma):** V0, pero el renglón también continúa si termina en coma.
- **V2 (ancho del documento):** se estima el ancho `W` del documento como la longitud del renglón más largo. Un renglón «se cortó por el ancho» si la primera palabra del siguiente no cabía: `largo(renglón) + 1 + largo(primera palabra del siguiente) > W`. El documento «viene partido» si al menos 4 renglones y al menos el 20 % de sus renglones con texto cumplen esa prueba. En un documento partido, un renglón cortado por el ancho se une con el siguiente, sin mirar mayúsculas ni puntuación. Las condiciones de V0 que no dependen de las letras se mantienen: el siguiente no es elemento de lista, ninguno es fila de tabla, el renglón no parece título. En un documento no partido se aplica V0.
- **V3:** V2 con la coma de V1 para los documentos no partidos.

## Cómo se elige (desarrollo)

- Material: bancos de G-59 a G-62 (1116 preguntas directas y de sí/no), conteo automático por claves, base de `estable-G-18`.
- Presentaciones: partido a 70 columnas (principal), partido a 50 y a 90 (para que no se ajuste a un ancho) y tal cual.
- Se elige la variante con más útiles a 70 entre las que cumplen:
  1. a 50 y a 90, no menos útiles que V0;
  2. tal cual, respuestas idénticas a `estable-G-18` en ≥ 98 % de los turnos;
  3. citas sin dato no más que V0 + 2 puntos.
- Confirmación en otro material de desarrollo: bancos de G-57, G-58 y desarrollo, partidos a 70. La variante elegida no debe quedar por debajo de V0 ahí.
- **Si ninguna variante supera a V0 a 70 por al menos 10 útiles (0,9 puntos) en desarrollo, se para aquí y no se gasta en banco nuevo.**

## Medida (si pasa desarrollo)

Congelado `freeze-G-64`; semilla de su huella. Banco congelado nuevo de 24 negocios de sectores distintos de los 192 anteriores, redactores nuevos con worktree y el encargo neutral de siempre, en git antes de ejecutar. Presentación partida a 70 columnas, como en G-63; a 55 columnas solo como diagnóstico automático.

**Juez ciego** (8 jueces nuevos, Opus, encargo de G-58): G-64 y `estable-G-18`, texto partido y tal cual.

**Puertas:** las mismas de G-63, sin cambios:
1. útiles en directa + sí/no con texto partido ≥ `estable-G-18` partido + 5 puntos;
2. texto tal cual: respuestas idénticas a `estable-G-18` en ≥ 98 % de los turnos y útiles no menores;
3. citas engañosas ≤ 15 % y no más de 2 puntos por encima de `estable-G-18`, en cada presentación;
4. 0 inventadas;
5. sin respuesta bien llevadas ≥ 90 %;
6. eco 0;
7. controles: sin unir (= `estable-G-18` partido), reinicio 100 %, otro negocio (útiles ≤ 5 %, «No lo sé» ≥ 80 %), renombrado estricto: se informa. En G-63 dio 89 %. Si la causa es que el renombrado cambia dónde se parte el texto, se mide también renombrando **antes** de partir, y ahí se pide ≥ 95 %.
8. Pruebas generales sin retroceso: MFAQ normalizado no menor, SQuAD-es ≥ 0,8013, conversación 158, regresión sin fallos, latencia.

**Tag estable:** si pasa, con auditoría 5.10.

## Presupuesto

Desarrollo ≤ 30 min de CPU, hasta 4 procesos, con al menos 2 GB de RAM libres. Banco ≤ 40 min; juez ≤ 1 h.
