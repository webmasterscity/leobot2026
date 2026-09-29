# G-115b: δ' fuera de pliegue al enseñar y calibrar (solo datos, motor `d1c92eb7…`)

Preregistro: `prereg/G-115b-delta-fuera-de-pliegue.md`.

## Desarrollo: pasa
Punto de operación, conteo automático, seis bancos gastados (N = 2230). Datos en `kiosco/g115b_desarrollo/`.

| Sistema | `cite_from` | Útiles | Citas malas |
|---|---|---|---|
| G-112 | 0,5167 | 731 | 414 |
| G-115 (δ' visto al calibrar) | 0,3971 | 1042 | 756 |
| **G-115b (δ' fuera de pliegue)** | **0,4831** | **864** | **397** |

- Por banco, G-115b frente a G-112 (útiles / malas):
  - `g103`: 138/60 frente a 127/66;
  - `g111`: 142/55 frente a 119/66;
  - `g112`: 163/62 frente a 134/66;
  - `g114`: 137/72 frente a 124/69;
  - `g114b`: 128/73 frente a 100/75;
  - `g115`: 156/75 frente a 127/72.
- Condiciones del preregistro:
  - útiles +133 = +5,96 puntos, cuando se pedían ≥ +3: **pasa**;
  - malas 397, cuando el tope era 414 + 22: **pasa**.
- Enseñanza: 225 s de CPU (6 extracciones y el ajuste), 4723 registros.

## Reserva: banco nuevo `congelado_g115b`, juez ciego doble. **Pasa los cuatro umbrales**
- Banco: 32 negocios y 802 turnos de 8 redactores independientes, con commit `7577089` antes de ejecutar.
- Jueces: A (Opus) y B (Sonnet) en 12 lotes, con 356 respuestas distintas. Los 17 desacuerdos (4,8 %) los resolvió un tercero (Opus).
- Datos: `kiosco/evaluacion_g115b/`. `b0.json` es el control G-112.

| | G-112 | G-115b |
|---|---|---|
| Útiles en directas + sí/no (N = 368, juez) | 111 (30,2 %) | **149 (40,5 %)** |
| Engañosas (todos los turnos) | 20 | **17** |
| Sin respuesta coherentes bien manejadas | 145/146 | **146/146** |
| Conteo automático, útiles | 104 | 135 |
| Conteo automático, citas sin dato / no útiles | 36 / 76 | 28 / 74 |
| `Bot.answer` p50/p95 | 1,46 / 2,63 ms | 1,37 / 2,17 ms |

Umbrales preregistrados:
1. **Pasa:** +10,33 puntos, con bootstrap por negocio [+6,32, +14,59].
2. **Pasa:** 17 engañosas, dentro del tope de 20 + 3,7.
3. **Pasa:** 100 %.
4. **Pasa:** reinicio idéntico (0 diferencias en 802 respuestas) y p95 de 2,17 ms.

**Veredicto:** es la primera mejora del kiosco que pasa todos sus umbrales en un banco nuevo con juez ciego desde G-64.
- Se propone G-115b como base del kiosco. Antes de un tag estable: regresión completa, latencia, tablero y auditoría 5.10.
- Motor sin cambios (`d1c92eb7…`): la mejora es **solo educación**, es decir, datos contados de los negocios de enseñanza.
- Reconstruir la base: `python3 -m experiments.g115b_educar .leobot-data/base_kiosco_nube.json .leobot-data/g115b.json`, con `PYTHONHASHSEED=0`, 225 s de CPU. El sha256 es `9ab69ae5…`.
