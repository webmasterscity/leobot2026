# G-32c — concordancia y palabra cabeza aprendidas para las funciones, con memoria medida por proceso

Fecha: 2026-09-23. Preregistro previo al cambio. Base: `freeze-G-32b` (`9e53c219`).

G-32b falló por dos criterios:
- **F1 de sujeto:** 0,591 frente a 0,60.
- **Memoria:** 901 MiB frente a 768. El evaluador mantenía tres bots educados en un proceso.

Análisis de errores en el desarrollo visible:
- El error dominante del sujeto es el sujeto **pospuesto** etiquetado como objeto: 36 casos, frente a 20 aciertos.
- Siguen las cabezas equivocadas, sobre todo nombres colgados de otro nombre como aposición.

## Cambios

1. **Motor.** Dos contextos nuevos, aprendidos por conteo, para la función de cada arco:
   - **Concordancia:** clases, dirección, última letra de la cabeza y última letra del dependiente. Se inserta antes del nivel de distancia con marcador.
   - **Tendencia de cada cabeza:** palabra cabeza vista ≥3 veces, clase del dependiente, dirección y marcador. Se inserta después del nivel de distancia con marcador.

   No hay reglas gramaticales escritas; las terminaciones y las palabras se cuentan. Exploración en desarrollo visible, que se declara:

   | Configuración | LAS | F1 de sujeto | F1 de objeto |
   |---|---|---|---|
   | G-32b | 0,7152 | 0,6132 | 0,6981 |
   | Con ambos contextos | 0,7185 | 0,6275 | 0,709 |

   Otras variantes probadas: la concordancia como contexto más específico bajó LAS a 0,674, y cada contexto por separado dio ganancias menores.

2. **Evaluador.** Los controles con su propio bot educado (etiquetas barajadas y cabezas barajadas) corren en procesos hijos. El RSS de la puerta es el máximo por proceso, así que mide un bot a la vez.

## Puerta

La de G-32, sin cambios:

| Criterio | Umbral |
|---|---|
| Clases | ≥ 0,92 |
| UAS | ≥ 0,75 y ≥ +0,01 sobre `freeze-G-31` en la misma reserva |
| LAS | ≥ 0,70 |
| F1 de sujeto | ≥ 0,60 |
| F1 de objeto | ≥ 0,60 |
| Función correcta con cabeza correcta | ≥ 0,85 |
| Ventaja sobre la ablación | ≥ 0,02 |
| Etiquetas barajadas | ≤ 0,40 |
| Cabezas barajadas | ≤ 0,35 |
| Fresco | sin análisis |
| Reinicio | idéntico |
| p95 | ≤ 100 ms |
| Educación | ≤ 240 s |
| RSS | ≤ 768 MiB por proceso |
| Hashseed 0 y 1 | idénticos |
| Huella | idéntica |

La reserva son 300 oraciones de `test`, con la semilla de `git rev-parse freeze-G-32c:leobot`. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Leobot confundía el sujeto con el objeto cuando el sujeto va después del verbo, como en «llegó el tren». Ahora aprenderá, contando ejemplos, dos pistas que usamos las personas: que sujeto y verbo suelen concordar, y que cada verbo tiene sus costumbres. Además, la prueba medirá la memoria de un solo Leobot por vez, no de tres juntos.
