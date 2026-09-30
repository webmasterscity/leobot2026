# G-115b: δ' fuera de pliegue para enseñar y calibrar el modelo de utilidad (solo datos, motor congelado)

- Fecha: 2026-09-29.
- Estado: diseñado. Precede al código y a toda medida.
- Motor sin cambios (huella `d1c92eb7…`).
- Motivo: G-115 (`results_v3/g115_resumen.md`) dio +18,4 útiles con juez en un banco nuevo, pero 32 engañosas frente a 17 y sin respuesta al 95,2 %.
- Causa registrada: δ' se contó en los mismos 216 negocios con que se enseñan y calibran el modelo G-112 y su umbral de cita. Así, las puntuaciones «cruzadas» usan un δ' que ya vio la respuesta correcta de ese negocio y la calibración es optimista (`cite_from` 0,397).

## Cambio (único)
- Los 216 negocios se reparten en los 5 grupos de G-103 (sha256, igual que `g103_educar`).
- Para cada grupo f, δ'₋f se cuenta sin los negocios de f, igual que en G-115 (reemplazo, respaldo por clase, `rare_delta`). Los registros de enseñanza de los negocios de f se extraen con una base que lleva δ'₋f.
- Con esos registros fuera de pliegue se hace todo lo de `g112_educar`: modelos cruzados por grupo, modelo final con todos, calibración isotónica y regla del umbral.
- **Presupuesto de citas malas de la regla:** el de la línea base B0 **con el δ original de la base** (como en G-112), no con δ'.
- La base final lleva el δ' completo (216 negocios), como G-115, y el modelo final así enseñado.

## Desarrollo (seis bancos gastados: `congelado_g103`, `_g111`, `_g112`, `_g114`, `_g114b`, `_g115`)
- Medida en el punto de operación con `experiments.g111b_evaluar.points`, sumando los seis bancos:
  - útiles: confianza ≥ `cite_from` y la unidad tiene las claves;
  - malas: confianza ≥ `cite_from` y no útil, incluidas las sin respuesta.
- Referencias: G-112 (`g112.json`) y G-115 (`g115_reemplazo.json`).
- Se pide banco nuevo solo si G-115b cumple las dos condiciones:
  - **útiles ≥ G-112 + 3 puntos de N** (N = turnos directa/sí-no con claves de los seis bancos);
  - **malas ≤ malas de G-112 + 0,01 N**.
- Si no las cumple, queda negativo en desarrollo y se registra.

## Reserva (si pasa)
- Banco `congelado_g115b`: 8 redactores independientes, con el encargo de G-115 y los sectores de `congelado_g115` añadidos a los excluidos.
- Juez ciego doble como en G-114b/G-115 (`g114_juez --coherentes`), comparando G-115b con G-112.
- Umbrales, iguales a G-115:
  1. útiles +3,0 puntos, con bootstrap que excluye 0;
  2. engañosas ≤ G-112 + 0,01 N;
  3. sin respuesta coherentes ≥ 97 %;
  4. p95 ≤ 5 ms y reinicio idéntico.

## Presupuesto
- Enseñanza ≤ 30 min de CPU: 6 extracciones de unos 2 min y el ajuste.
- Evaluación de desarrollo ≤ 30 min.
