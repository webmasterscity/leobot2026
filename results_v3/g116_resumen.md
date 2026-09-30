# G-116 y G-116b: correcciones verificadas y comparación con la base real

Fecha: 2026-09-29. Preregistros: `prereg/G-116-correcciones-y-comparacion-con-base-real.md` y `prereg/G-116b-compatibilidad-de-bibliotecas-y-calibracion.md`.

La integración conserva la base real. G-115b mejora las citas útiles, pero aumenta las citas malas y tarda más que la base actual. No recibe promoción ni un tag estable. Son siete bancos conocidos: este resultado es desarrollo, no una reserva nueva ni un juicio humano de utilidad.

## Correcciones

- Las plantillas y la búsqueda por relaciones actualizan la negación aprendida antes de comprobar la primera pregunta tras una nueva enseñanza y no afirman preguntas negadas sin respaldo. Si no pueden comprobarlas, se abstienen; las preguntas positivas siguen funcionando.
- La biblioteca valida toda la estructura antes de cambiar memoria. Admite las varias raíces que produce el propio analizador, rechaza índices y ciclos inválidos, y reemplaza análisis fallidos.
- El formato 2 conserva las palabras analizadas, para cargar con otra base. El formato 1 sigue disponible; si cambió la separación, se conserva el texto sin usar ese análisis.
- Una carga rechazada tampoco consolida la sintaxis del receptor. Las filas de biblioteca siguen excluidas de la memoria guardada.
- La base antigua conserva la recuperación con la que aprendió su confianza. Las nuevas calibraciones guardan la opción de prefijos; el modelo de candidatas y las elecciones explícitas siguen funcionando.

## Comparación reproducida

p95 —tiempo máximo del 95 % de las respuestas— se mide sin incluir la carga inicial.

2596 preguntas directas o de sí/no, dentro de 5792 turnos. Las citas malas se cuentan en todos los turnos. Los aciertos se cuentan por claves y no sustituyen al juez ciego.

| Sistema | Citas útiles | Citas malas | p95 de respuesta (ms) | Memoria máxima individual (MiB) |
|---|---:|---:|---:|---:|
| Base real estable | 802 | 733 | 0.248 | 623.6 |
| Base real con prefijos activados | 898 | 876 | 0.274 | 616.3 |
| G-112, educación de nube | 805 | 825 | 1.602 | 426.6 |
| G-115b, educación de nube | 951 | 794 | 1.598 | 426.7 |
| G-112, educación real | 864 | 847 | 1.641 | 512.5 |
| G-115b, educación real | 1022 | 833 | 1.647 | 512.6 |

G-115b con educación real gana 220 citas útiles (+8,475 puntos), pero suma 100 citas malas: falla el criterio registrado. Activar prefijos sobre la base antigua tampoco pasa. Ninguna candidata sustituye la base actual.

## Verificación, costo y límites

- Regresión completa final: 697 pruebas, 6 fallos esperados y ningún fallo inesperado, Python 3.12.3; 97,4 s transcurridos. Nuevas pruebas fallaron antes de sus correcciones. No se modificaron pruebas ni evaluadores anteriores a la revisión.
- Compatibilidad: las 585 respuestas y sus estados son idénticos a la base estable local, sin interruptores del evaluador.
- Reconstrucción de nube: base inicial con otra serialización; G-115b final SHA `9ab69ae5cbb5a43ef37b3a428259d351b66ec0b7eec1d1de59798f54b45b464e`, coincidente con el prefijo histórico. Las 802 respuestas y estados de su banco archivado se reproducen sin diferencias.
- Reinicio en procesos nuevos y hashes 0/1/2: respuestas idénticas en 802 turnos para cada una de las dos bases G-115b.
- Enseñanza de cuatro bases: 453,919 s CPU, memoria máxima individual 974,6 MiB; inferencia y enseñanza se miden por separado. Base general de nube: 59,2 s CPU; educación/calibración: 12,5/4,8/9,6 s transcurridos. No se instrumentó toda la CPU de esas tres etapas ni de las regresiones; estos tiempos no equivalen a un costo total completo.
- La primera auditoría independiente confirmó negación y señaló dos incompatibilidades de biblioteca y un efecto al validar. Se corrigieron. El supuesto de una sola raíz introducido en una prueba nueva era incorrecto; la auditoría y el resultado inicial se conservaron. La segunda solicitud de auditoría Claude no pudo ejecutarse por límite semanal; su salida se conserva. La revisión técnica complementaria encontró un negador recién aprendido que aún no se aplicaba a la primera pregunta. Se añadió una prueba que falló antes y pasó después, se corrigió el orden de actualización y el revisor confirmó el cierre del hallazgo. Su dictamen permite integrar las correcciones; no equivale a cerrar la auditoría científica 5.10.
- Las primeras mediciones de memoria acumulaban procesos y las primeras pruebas de latencia compartieron núcleo. Se conservaron como diagnóstico; las cifras de esta tabla usan procesos separados y las pruebas finales de latencia se ejecutaron en serie.
- Motor congelado durante la enseñanza: `c9359662c19c22e41d250ff9d8fc3630dbe328f6`; durante la comparación aislada: `630b777997638a728410f1dffe89951bfeb3437d`; verificación final después de corregir la negación incremental: `0248198c417ece64b827709ec9c59253a995f878`.

## Latencia y capacidad general

- Semilla 0: 100 000 hechos; conocido p50/p95 0.07768/0.08773 ms; razonamiento p95 0.16859 ms; memoria 219.5 MiB. Todos los límites y respuestas pasan.
- Semilla 1: 100 000 hechos; conocido p50/p95 0.07794/0.08402 ms; razonamiento p95 0.17200 ms; memoria 219.9 MiB. Todos los límites y respuestas pasan.
- Semilla 2: 100 000 hechos; conocido p50/p95 0.07850/0.08731 ms; razonamiento p95 0.16858 ms; memoria 219.6 MiB. Todos los límites y respuestas pasan.

La porción fija de lectura de MLQA mantiene 0/20 con un bot sin educación. No se demuestra una mejora de comprensión general, AGI ni ASI. ARC sigue pausado. Último estado estable: `estable-G-19`, motor `11a1ef5836382d81a643cad0b217a8669ce0f2d1`; no se crea otro. El siguiente avance del kiosco debe mejorar la utilidad sin perder prudencia y después pasar una reserva nueva y auditoría independiente.

## Repetir la comparación

```bash
PYTHONHASHSEED=0 timeout 600s python3 -m experiments.g115b_educar .leobot-data/base_kiosco.json .leobot-data/revision_g116/g115b_real.json
PYTHONHASHSEED=0 timeout 300s python3 -m experiments.g116_comparar results_v3/g116b/repeticion actual=.leobot-data/base_kiosco.json actual_on=.leobot-data/base_kiosco.json g115b_real=.leobot-data/revision_g116/g115b_real.json
```

## En palabras fáciles de entender

El programa ya no dice que sí cuando una pregunta niega algo que no puede comprobar. También puede cargar libros preparados sin olvidar las frases válidas ni quedarse a medias cuando encuentra un archivo dañado. La versión que Leonardo usa conserva sus respuestas. Se volvió a enseñar otra versión y se la comparó con la actual: ayuda en más preguntas, pero se equivoca en más casos, así que se conserva como una prueba y no se pone a atender personas. Los arreglos mejoran la confianza que podemos tener en el programa; todavía no demuestran que comprenda mejor cualquier tema.
