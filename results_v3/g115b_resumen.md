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

## Reserva
Pendiente: banco `congelado_g115b`, juez ciego doble.
