# G-114b: la réplica de G-114 en el banco 5 sale **negativa**. La ventaja de G-112 sobre B0 no se reproduce

- Preregistro: `prereg/G-114b-replica-con-juez.md` (commit `e719c48`, antes del banco).
- Motor sin cambios: huella `d1c92eb7…`, la misma antes y después.
- Sistema: `.leobot-data/g112.json`.
- Banco nuevo `congelado_g114b`:
  - 32 negocios y 842 turnos, escritos por 8 redactores independientes;
  - commit `8f62ea1`, hecho antes de ejecutar Leobot sobre él.
- Juez:
  - el mismo encargo que en G-114;
  - 384 respuestas distintas, mezcladas y anónimas, en 13 lotes;
  - jueces A (Opus) y B (Sonnet) en cada lote; los 20 desacuerdos (5,2 %) los resolvió un tercero (Opus).
- Datos: `kiosco/evaluacion_g114b/`. La clave y los veredictos están en `juez/`.

| | B0 | G-112 |
|---|---|---|
| Útiles en directas y sí/no con acción «responder» (N = 357) | **111 (31,1 %)** | 106 (29,7 %) |
| Engañosas (todos los turnos) | 19 | 20 |
| Sin respuesta coherentes bien manejadas | 145/149 | 149/149 |
| Conteo automático por claves (útiles) | 107 | 100 |
| `Bot.answer` p95 | — | 2,33 ms |

Umbrales preregistrados:
1. **Falla.** La diferencia es −1,40 puntos, con bootstrap por negocio [−5,07, +2,35].
2. **Pasa.** Engañosas: 20 ≤ 19 + 3,6.
3. **Pasa.** 149/149 = 100 %.
4. **Pasa.** El reinicio es idéntico (0 diferencias en 842 respuestas) y el p95 es 2,33 ms, dentro de los 5 ms.

**Veredicto: negativo.** G-112 no se propone como modelo del kiosco, y el resultado de G-114 se conserva tal cual.

## Qué dice el conjunto de bancos nuevos
Diferencia G-112 − B0, banco por banco y según quién mide:

| Banco | Medida | Diferencia |
|---|---|---|
| `congelado_g103` | juez (modelo G-103) | +6,5 |
| `congelado_g111` | automático | +5,2 |
| `congelado_g112` | automático | +2,4 y +0,55, según el presupuesto |
| `congelado_g114` | juez | **+8,1** [+3,4, +12,7] |
| `congelado_g114b` | juez | **−1,4** [−5,1, +2,4] |

- Juntando G-114 y G-114b (lectura descriptiva, no es un criterio): 235/717 frente a 211/717, es decir, +3,3 puntos.
- El efecto depende del banco: varía entre redactores y sectores más de lo que el intervalo de cada banco deja ver.
- El modelo denso sí mejora algo de forma constante: callar cuando no hay dato (sin respuesta 149/149 y 156/161). En cambio, no mejora con fiabilidad la elección de la unidad que responde.
- Esto confirma el diagnóstico de G-106 y G-113: la curva de aprendizaje es plana y el hueco es de capacidad («no pudo»), no de datos.

## No repetir
- Un banco más con el mismo sistema G-112: la varianza entre bancos ya está medida.
- Otro umbral de cita, u otros rasgos léxicos o por palabra en el modelo denso: G-104 a G-112 ya lo intentaron.
