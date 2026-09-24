# G-39c — colores como símbolos: DSL tipado para cuadrículas

Fecha: 2026-09-23. Preregistro previo al código del motor. Tercer diseño para ARC. Base: `freeze-G-39b` (`cb8fcdb1`). Último estable: `estable-G-9`.

## Fallo y causa

G-39b resolvió 3/200 de la reserva con 0 errores, pero falló el control de renombrado de colores: 5 aciertos y 1 error, frente a 3.

La causa es que el motor trata los colores como números:
- hace aritmética con ellos (por ejemplo, `floordiv(6, comp(r,c))` o `max(0, at(...))`);
- desempata «el color más frecuente» por el color de menor valor.

Un programa así depende del número que codifica cada color, no de la estructura. Para una persona los colores son nombres: se copian y se comparan, pero no se suman.

## Cambio (5.8), en `leobot/programs.py`

**Tipos en la búsqueda (`fit`).** Cada expresión es `num` o `color`.
- **Tipo `color`:**
  - `at(i,j)`;
  - las variables color más frecuente, color distinto de cero más frecuente y menos frecuente;
  - las constantes de color.
- **Tipo `num`:**
  - el resto de variables (fila, columna, alto, ancho, número de colores y recuadro);
  - las constantes -1, 0 y 1;
  - `nb` y `comp`.
- La aritmética y los índices de `at`, `nb` y `comp` solo aceptan `num`.
- Las firmas se distinguen por tipo.
- Una solución de celda tiene que ser de tipo `color`.
- Los programas de alto y ancho solo usan variables `num`.

**Constantes de color.** Son los colores que aparecen en las salidas de los ejemplos, tomados de los datos y no fijados de antemano. Se cambian al renombrar, igual que la tarea.

**Fuera de la cuadrícula**, `at` devuelve un símbolo que no es ningún color.

**Desempates** del color más frecuente y del menos frecuente: por la primera aparición en orden de lectura, no por el valor.

El resto no cambia respecto de G-39b: agregados, inversión de `at`, presupuestos, sondas y abstención.

**Consecuencia esperada:** se pierden tareas que solo se resolvían por coincidencias numéricas, y el renombrado de colores deja el resultado igual por construcción. Solo pueden quedar diferencias por el tiempo, porque cambia el orden de las constantes.

5.8:
- **Qué fallo resuelve:** dependencia de la codificación de los colores.
- **Por qué no bastan los actuales:** el DSL no tiene tipos.
- **Qué lo distingue:** el control de renombrado y la ablación sin tipos (G-39b tal cual).
- **Qué se elimina:** la aritmética sobre colores.

## Datos, controles y puerta

Iguales a G-39b:
- reserva de 200 tareas de `evaluation` con la semilla de `freeze-G-39c`;
- presupuesto: 6 s, tamaño 7, 120 000 candidatos y 10 M valores;
- 2 procesos.

Controles: los de G-39b, más la ablación **sin tipos**, que es el motor de G-39b con las mismas tareas.

| Criterio | Umbral |
|---|---|
| Aciertos en la reserva | ≥ 3/200 |
| Precisión | ≥ 0,8 |
| Ventaja sobre la mejor ablación sin inversión o sin agregación | ≥ +2 |
| Sin `at` | ≤ 1 acierto |
| Pares barajados | 0 aciertos |
| Colores renombrados | ±1 del tratamiento |
| Reinicio | idéntico |
| Fresco | sin respuesta |
| Predicción p95 | ≤ 200 ms |
| Aprendizaje | ≤ 30 s de CPU por tarea |
| RSS | ≤ 1500 MiB por proceso |
| Regresión | sin fallos nuevos |
| Latencia fija | ≤ +20 % frente a `estable-G-9` |

Si falla, es el tercer diseño para ARC y se evalúa si la vía queda refutada según la regla de la sección 6.

## En palabras fáciles de entender

En los rompecabezas, los colores son como nombres: rojo o azul. El intento anterior a veces «sumaba» colores como si fueran números y acertaba por casualidad. Por eso, al cambiar los colores de un rompecabezas, su resultado cambiaba, y eso no debería pasar. Ahora Leobot solo podrá copiar colores, no hacer cuentas con ellos. Las cuentas quedan para posiciones, tamaños y cantidades.
