# G-40 — objetos como vistas de la cuadrícula, compuestas con el aprendiz de celdas

Fecha: 2026-09-24. Preregistro previo al código del motor. Base: `freeze-G-39d` (`8355569d`). Último estable: `estable-G-10`.

## Fallo y causa

G-40-0 mostró que en ARC manda la representación: con 5 veces más cómputo, 5/100 siguen siendo 5/100. El aprendiz de celdas (G-39c/d) no puede expresar «recorta el objeto mayor» ni «recorta el único objeto de su color».

Fuentes, verificadas el 2026-09-24: el trabajo centrado en objetos de [Joffe y Eliasmith](https://arxiv.org/abs/2511.08747), y el [informe de ARC Prize 2024](https://arxiv.org/html/2412.04604v2), según el cual componer transformaciones de la cuadrícula entera es lo que usan los DSL de búsqueda.

**Exploración ya hecha**, fuera del motor y solo con `training` de ARC-AGI-1 ([prototipo](../experiments/g40_objects_prototype.py), [resultado](../results_v3/g40_objects_prototype_training.json)):
- **24/400 aciertos, 0 errores**, frente a 18/400 y 1 error del motor G-39d con el mismo desarrollo;
- 8 tareas nuevas, todas recortes a un objeto elegido por una propiedad o a todo el dibujo;
- 2 perdidas, por el menor tiempo por vista y por una abstención.

## Cambio (5.8), en `leobot/programs.py`

**Sustrato genérico de objetos**, con el 0 como fondo, como ya declaraba G-39b. Un objeto es un conjunto 8-conexo de celdas no vacías, con dos nociones:
- del mismo color;
- de cualquier color («mixto»).

**Vistas** de una cuadrícula:
- la identidad;
- el recuadro de todo lo dibujado;
- el recuadro del objeto elegido por una propiedad (el mayor, el menor, el de más arriba, el de más a la izquierda, el único con su conjunto de colores), para cada noción.

Si la elección no es única, la vista no existe para esa cuadrícula.

**Composición.** Nuevo `fit_grid_views`: para cada vista aplicable a todas las entradas de ejemplo y de prueba, aprende con `fit_grid` (G-39c/d, sin cambios) sobre (vista(entrada), salida).

**Respuesta.** `predict_grid_views` reúne las vistas que aprendieron y responden:
- si todas dan la misma cuadrícula, responde;
- si discrepan, se abstiene (`ambiguous`);
- si ninguna responde, `unknown`.

Presupuesto por vista: 2 s por habilidad. Lo demás no cambia: 120 000 candidatos y 10 M valores.

5.8:
- **Qué fallo resuelve:** no hay objetos ni composición de cuadrícula entera.
- **Por qué no bastan los actuales:** G-40-0.
- **Qué lo distingue:** la ablación «solo identidad», con el mismo presupuesto por vista.
- **Qué se elimina:** nada. Las vistas envuelven lo existente.

## Datos y reserva

Solo tareas **nunca usadas** en ningún ciclo:
- las 48 de la evaluación de ARC-AGI-1 que quedan libres ([usadas](../results_v3/arc1_evaluation_used_tasks.json));
- las 114 de la evaluación de ARC-AGI-2 que no están en ARC-AGI-1 (`arcprize/ARC-AGI-2@f3283f72`);
- las 233 del entrenamiento de ARC-AGI-2 que no están en ARC-AGI-1.

Son 395 en total. La reserva es de **150**, elegidas con la semilla de los primeros 8 hexadecimales de `git rev-parse freeze-G-40:leobot`. Se informa el resultado por origen.

Un proceso, hashseed 0; con hashseed 1 solo si pasa.

## Controles

- **Solo identidad**, con el mismo presupuesto por vista: equivale a G-39d.
- **Pares barajados.**
- **Colores renombrados**, con el 0 fijo.
- **Reinicio** (guardar y cargar) y **fresco**.

## Puerta

| Criterio | Umbral |
|---|---|
| Aciertos en la reserva | ≥ solo identidad + 2 |
| Precisión | ≥ 0,8 |
| Pares barajados | 0 aciertos |
| Colores renombrados | ±1 del tratamiento |
| Reinicio | idéntico |
| Fresco | sin respuesta |
| Predicción p95 | ≤ 200 ms |
| Aprendizaje | ≤ 60 s de CPU por tarea |
| RSS | ≤ 1500 MiB |
| Regresión | sin fallos nuevos |
| Latencia fija | ≤ +20 % frente a `estable-G-10` |

Se informan la brecha con la referencia pública de frontera y las tareas nuevas por tipo. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Muchos rompecabezas piden «quedarse con la figura más grande» o «con la única de otro color». Leobot aprenderá a ver las figuras de una cuadrícula y a mirar solo una de ellas antes de buscar la regla. En la práctica eso sumó 6 rompecabezas resueltos, sin ningún error. Ahora hay que comprobarlo en rompecabezas que nunca vio.
