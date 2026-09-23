# G-35 — separar contracciones y pronombres pegados aprendiendo del corpus, para analizar texto crudo

Fecha: 2026-09-23. Preregistro previo al código. Base: `estable-G-4` (`6b229755`).

## Fallo y causa

La sintaxis aprendida (UAS 0,768; LAS 0,722) se midió sobre palabras **ya separadas** por el corpus: «del» llega como «de» + «el», y «hacerlo» como «hacer» + «lo». Leobot lee texto crudo con una separación que no parte esas formas. La auditoría 5.10 de G-29 lo señaló: 733 de las 1722 oraciones de `test` tienen tokens multipalabra.

La lectura de MLQA y cualquier uso futuro de la estructura trabajan sobre texto crudo. Hoy no se sabe cuánto se degrada ahí el análisis.

## Hipótesis y alternativa

La separación se aprende contando las filas multipalabra de UD AnCora `train` (forma superficial → palabras):
- **Formas vistas:** tabla de las formas vistas ≥2 veces, con su separación más frecuente.
- **Formas nuevas:**
  - Se usan reglas de terminación inducidas de los pares observados. La terminación de la superficie se reescribe como la terminación de la primera palabra más las palabras siguientes; por ejemplo, «…rlo» → «…r» + «lo».
  - Una regla solo se aplica si tiene ≥3 apoyos distintos, si la primera palabra resultante fue vista en la educación y si la terminación se separó en ≥90 % de las palabras de la educación que la tienen.
- **Sin listas:** no se escribe ninguna lista de contracciones ni de pronombres.

Alternativa: las reglas generalizan mal (separan palabras que no deben), o el análisis sobre texto crudo apenas se degrada, así que separar no aporta.

5.8:
- **Fallo que resuelve:** la sintaxis no sirve igual en texto crudo.
- **Por qué no bastan los actuales:** la separación por expresión regular no parte contracciones ni pronombres pegados.
- **Qué lo distingue:** la comparación con la separación por expresión regular y con solo la tabla.
- **Qué se elimina:** nada.

## Evaluación

**Datos:**
- Educación: `train`, con el mismo modelo sintáctico de G-32c.
- Reserva: 300 oraciones de `test` de ≤60 palabras, con la semilla de `git rev-parse freeze-G-35:leobot`. Se excluyen las 1 000 oraciones usadas en reservas anteriores de G-29 a G-32c, informadas por su identificador.
- La entrada es el texto crudo de la línea `# text` de cada oración.

**Métricas:**
- F1 de palabras frente a las palabras del corpus.
- UAS y LAS sobre texto crudo, alineando palabra a palabra por posición en el texto. Una palabra mal separada cuenta como error.
- Diagnóstico: los mismos UAS y LAS con las palabras del corpus.

**Controles:**
- separación por expresión regular (la de hoy);
- solo la tabla, sin reglas;
- reglas barajadas: terminaciones asignadas al azar;
- fresco: sin separación aprendida;
- reinicio;
- hashseed 0 y 1.

**Puerta:**

| Criterio | Umbral |
|---|---|
| F1 de palabras | ≥ 0,98 |
| Ventaja de UAS sobre texto crudo frente a la expresión regular | ≥ 0,02 |
| Ventaja de UAS frente a solo la tabla | ≥ 0 |
| Distancia del UAS a la cifra con palabras del corpus | ≤ 0,03 |
| Reglas barajadas | no superan a la expresión regular |
| Latencia de la separación | ≤ 1 ms p95 por oración |
| Análisis completo p95 | ≤ 100 ms |
| Educación | ≤ 240 s |
| RSS | ≤ 768 MiB por proceso |
| Reinicio | idéntico |

Se archivan los resultados de desarrollo antes de congelar. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

En los ejemplos con que Leobot aprendió gramática, «del» ya venía partido en «de el» y «hacerlo» en «hacer lo». En un texto real no viene así, y eso lo confunde. Ahora aprenderá a partir esas palabras mirando cómo lo hicieron los expertos en los ejemplos, sin que nadie le dé una lista. Mediremos si así entiende mejor la gramática de textos reales.
