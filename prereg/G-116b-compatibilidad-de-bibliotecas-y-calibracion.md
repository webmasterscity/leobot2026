# G-116b: compatibilidad de bibliotecas y de la confianza aprendida

- Fecha: 2026-09-29. Continúa el encargo de corregir la rama; no cambia criterios de G-116.
- G-116 negativo: G-115b con la base real da 1022/2596 citas útiles frente a 802, pero 833 citas malas frente a 733. No reemplaza la base real. Son siete bancos gastados, no reserva nueva.
- La auditoría independiente refutó la exigencia de una sola raíz en la biblioteca: el analizador existente produce varias. La nueva prueba que calificaba ese caso como inválido contenía un supuesto erróneo; se corrige con una prueba de aceptación de la salida real, conservando el fallo y su explicación. No se modifica ningún evaluador o prueba anterior a esta revisión.

## Correcciones y comprobación

1. Una biblioteca admite árboles separados, siempre sin ciclos, índices fuera de rango ni tamaños incompatibles. La versión nueva guarda las palabras tal como se analizaron; sigue leyendo la versión anterior. Un análisis antiguo con separación distinta se omite, conservando su texto. Los análisis estructuralmente inválidos siguen rechazándose antes de cambiar memoria.
2. La validación se hace sobre una vista aparte cuando separar palabras requiere consolidar la sintaxis; un rechazo tampoco cambia ese estado derivado.
3. Una confianza antigua enseñada sin el modelo de candidatas no activa coincidencias por prefijos al cargar. El modelo nuevo las activa cuando se usa, y una elección explícita sigue prevaleciendo. Las futuras calibraciones guardan qué recuperación usaron. Control: 585 respuestas idénticas a la base estable real, sin interruptores del evaluador, y respuestas de las candidatas G-116 conservadas.
4. Añadir el control de la base real con prefijos activados a la comparación. La memoria se mide por sistema en procesos separados. Repetir la prueba fija de latencia en serie, porque las tres primeras corridas compartieron el mismo núcleo.

- Primero comprobar los fallos nuevos; después corregir. Pruebas rápidas ≤40 s, regresión ≤600 s, comparación ≤300 s, latencia ≤90 s por semilla. Motor congelado durante cada ensayo, sin nueva enseñanza ni cambios de umbrales. Se solicitará revisión de las correcciones de la auditoría.
- Solo se integrarán correcciones verificadas y herramientas de reproducción. Ninguna candidata aprendida recibe promoción por estas comprobaciones.

## En palabras fáciles de entender

La revisión encontró que el programa rechazaba algunos libros que él mismo había preparado. Se arregla guardando también cómo había separado las palabras y aceptando las formas válidas que ya produce. Además, al cargar la versión antigua conservará la manera de buscar con la que aprendió cuándo responder. Las versiones recién enseñadas siguen como pruebas: ayudan en más preguntas, pero también se equivocan más, por lo que todavía no deben sustituir la versión que Leonardo usa.
