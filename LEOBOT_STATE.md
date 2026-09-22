# LEOBOT_STATE — continuidad compacta

## Versión comprobada

- Leobot **0.3.9 / V3.9**.
- Python 3.13.5, CPU, sin redes neuronales/LLM/GPU en interpretación, adquisición, razonamiento o respuesta.
- Regresión actual: **131/131** pruebas.
- V3.8: `results_v3/v38_concept_invention.json`.
- V3.9: `results_v3/v39_predicate_invention.json`.
- Hash congelado actual `leobot/*.py`: `ce8a25ebfbb6c7701afe65a62b0051d10942caed3c9c953e2d4f8e24cae1398d`.

## Cambio aceptado V3.8 — invención grounded de conceptos relacionales

1. `ConceptGrounder` recibe afirmaciones naturales con exactamente dos entidades ya conocidas y polaridad explícita; el predicado objetivo no se entrega.
2. La superficie se deslexicaliza, se crea un identificador opaco `concept_*` y ejemplos positivos/negativos alimentan el aprendiz relacional existente.
3. El concepto se promociona solo con evidencia contrastiva mínima; pares no demostrados siguen siendo `unknown`, no `false`.
4. Una formulación nueva puede vincularse como alias de un concepto previo con menos ejemplos solo cuando existe una única relación aprendida compatible con evidencia positiva y negativa.
5. Contraevidencia posterior retira solo el alias, no el concepto raíz.
6. Los conceptos inventados se convierten en primitivas disponibles para aprender conceptos de orden superior.

### Evidencia V3.8

- Concepto opaco aprendido como `parent ; parent`: 100/100 positivos held-out, 0 falsos positivos sobre 100 negativos.
- 5.000 predicados distractores disjuntos no entraron en el conjunto relevante del entrenamiento.
- Reserva estructural distinta: descubrió `inverse(teach)` y transfirió a entidades nuevas.
- Nueva superficie con concepto previo: 100/100 tras 1 positivo + 1 negativo; desde cero con los mismos dos ejemplos: 0/100.
- Concepto `r;s` previo permitió aprender un concepto `r;s;r;s` bajo profundidad 2; sin la abstracción previa y con el mismo presupuesto quedó sin solución.
- Persistencia Bot/SQLite comprobada; ruta conversacional de consulta comprobada.

## Cambio aceptado V3.9 — invención autónoma y reutilizable de predicados auxiliares

1. Cuando la inducción directa termina completa pero sin solución, `fit_with_invention` puede explorar una cantidad finita de predicados auxiliares binarios cortos.
2. El auxiliar no recibe nombre semántico ni patrón del dominio; se construye sobre predicados relevantes del problema.
3. Solo se conserva si el programa final del objetivo depende realmente de él. Los intentos fallidos se retiran.
4. La recuperación de predicados expande un vecindario relacional acotado para incluir relaciones que solo aparecen en nodos intermedios, sin escanear toda la memoria.
5. Predicados que tocan ejemplos positivos se priorizan frente a relaciones presentes solo en negativos; composiciones directas se prueban antes de inversiones.
6. Reglas de camino aprendidas se compilan como composiciones directas y se cachean durante la transacción de aprendizaje, evitando ejecutar siempre el motor lógico general.

### Evidencia V3.9

- Objetivo `r;s;r;s` con profundidad directa 2: control sin invención 0/100; V3.9 inventó `r;s` en 2 intentos y obtuvo 100/100.
- Coste total de la primera invención en la corrida final: ~19,8 ms, 178 candidatos de objetivo acumulados; búsqueda directa profundidad 4: ~13,3 ms, 150 candidatos. La primera invención **todavía tiene sobrecoste**.
- El auxiliar persistió tras reinicio y, con nueva invención desactivada, permitió aprender otro objetivo `r;s;t` con profundidad 2: 100/100.
- Mismo segundo objetivo sin auxiliar bajo profundidad 2: 0/100. Con profundidad 3 directa: 100/100.
- Reutilización del auxiliar: ~14,8 ms / 168 candidatos frente a ~15,7 ms / 184 candidatos para profundidad 3 directa en esa corrida. Reduce profundidad y ligeramente candidatos, pero todavía no demuestra una ventaja estable de latencia.
- Aprendiz congelado durante V3.8/V3.9: hashes antes/después idénticos en los experimentos.

## Antecedentes cercanos

La invención de predicados no es nueva. Meta-Interpretive Learning (Muggleton, Lin & Tamaddoni-Nezhad, 2015), trabajos posteriores de Cropper/Morel/Muggleton y POPPI estudian predicados inventados y reutilización lógica. La aportación experimental aquí es local: conexión con español grounded, alias contrastivos, routing por relevancia, memoria escalable y reutilización de la representación inventada en el mismo bot. No se afirma originalidad histórica general.

## Cuello de botella principal

Leobot ya puede inventar una relación nombrada por una superficie natural y, si hace falta, un auxiliar lógico intermedio. Sin embargo:

- sigue restringido a relaciones binarias y a un DSL de caminos/inversión/cierre;
- las entidades deben existir previamente en memoria para el grounding conceptual;
- el significado base proviene de hechos/predicados estructurados; texto bruto arbitrario todavía no crea automáticamente un mundo conceptual abierto;
- la invención inicial puede costar más que una búsqueda profunda directa;
- lenguaje libre, creación abierta y resolución general permanecen muy por debajo de un LLM de frontera.

## Hipótesis activa siguiente

**Representación relacional de aridad abierta / adquisición de esquemas desde texto y experiencia sin predicado ni aridad objetivo predefinidos.**

Experimento mínimo propuesto: extender la formación de conceptos a relaciones de 1–3 roles donde el número y orden de roles se infieran de experiencias naturales contrastivas; demostrar transferencia a entidades y formulaciones nuevas y que una representación aprendida facilite una segunda tarea. Comparar contra memoria episódica, contra versión binaria y contra un control con aridad/roles entregados manualmente.

Criterio de descarte: si el mecanismo solo funciona porque una heurística textual fija decide la aridad/roles o si la búsqueda explota antes de transferir a estructuras no vistas, no promoverlo como avance general.

## Límites / meta

- AGI demostrada: **NO**.
- ASI demostrada: **NO**.
- No hay evidencia de crecimiento cognitivo ilimitado.
- Evaluaciones siguen siendo internas y sintéticas; reserva realmente independiente pendiente.
- El objetivo de sustituir LLM de frontera sigue vigente, pero ninguna métrica actual justifica declarar equivalencia general.
