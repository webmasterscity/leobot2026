# G-40-0 — diagnóstico: ¿el límite de ARC es el cómputo o la representación?

Fecha: 2026-09-24. Preregistro de un diagnóstico, sin cambio del motor. Motor: `freeze-G-39c` (`bcdbc28f`).

## Pregunta

El [informe de ARC Prize 2024](https://arxiv.org/html/2412.04604v2) dice que cualquier búsqueda de programas mejora con más cómputo, y que la fuerza bruta en un DSL llegó al 40 % con mucho cómputo. G-39c usa 6 s por habilidad, en Python.

- Si con 5 veces más presupuesto sube claramente la cantidad de tareas de práctica resueltas, el límite actual es sobre todo de eficiencia de búsqueda.
- Si apenas sube, es de representación: faltan objetos y composición.

El resultado orienta G-40 (objetos) y G-41 (biblioteca aprendida). No se promueve nada: la misión prohíbe subir límites para avanzar, y esto solo mide.

## Diseño

- **Tareas:** 100 de `training` de ARC-AGI-1 (`fchollet/ARC-AGI@39903044`), elegidas con la semilla fija 4040. No se usa `evaluation`.
- **Presupuestos:**
  - ×1: 6 s, 120 000 candidatos y 10 M valores por habilidad (el de G-39c);
  - ×5: 30 s, 600 000 candidatos y 50 M valores.
  - Un proceso, hashseed 0.
- **Métricas:** aciertos, errores, abstenciones, CPU por tarea, RSS y en qué etapa falla cada tarea.
- **Lectura del resultado, fijada de antemano:**
  - «el cómputo pesa» si con ×5 los aciertos suben un 50 % o más respecto de ×1;
  - «la representación manda» si suben menos de un 20 %;
  - entre ambos, mixto.

## En palabras fáciles de entender

Antes de cambiar a Leobot, queremos saber si falla por pensar poco tiempo o por no tener las ideas necesarias. Le daremos cinco veces más tiempo en 100 rompecabezas de práctica: si mejora mucho, le falta velocidad; si casi no mejora, le faltan ideas nuevas, como reconocer objetos.
