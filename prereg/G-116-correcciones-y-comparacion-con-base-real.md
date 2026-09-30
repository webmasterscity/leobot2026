# G-116: correcciones de la revisión y comparación con la base real

- Fecha: 2026-09-29. Pedido: continuar y mejorar la rama revisada.
- Punto de partida: `1f22417`; motor `d1c92eb74b5d58420fc698aec30ea334bd1ad27d`.
- No se añade un subsistema ni se cambian pruebas o resultados anteriores.

## Hipótesis y correcciones

1. Las plantillas de conocimiento general ignoran la negación aprendida. No deben afirmar una relación negada sin comprobarla; la abstención es admisible. Las consultas positivas deben conservarse y las rutas generales seguir apagadas por defecto.
2. Una biblioteca compilada válida debe reemplazar un análisis fallido anterior. Una biblioteca inválida debe rechazarse antes de modificar frases, análisis o índices. Se comprobarán longitudes, índices, raíces y ciclos del análisis; las filas sin análisis siguen siendo válidas.
3. La mejora de G-115b reside en una base aprendida, no en fusionar código. Se reconstruirán el control G-112 y G-115b tanto desde la educación de nube como desde la base real del usuario, sin sobrescribir esta última.

## Datos y controles

- Educación: los mismos 216 negocios de `g115_delta_documento.teaching_folders`; semillas de enseñanza y `PYTHONHASHSEED=0`. No usar bancos posteriores para enseñar.
- Reconstrucción de nube: AnCora y SQuAD-es locales, fuentes verificadas; no descargas ni dependencia nueva.
- Base real: `.leobot-data/base_kiosco.json`, SHA `6fff61c20fcd5812d785eec22b6c595e19568f98ec31559e689c7fb95fe6d79f`, sin modificaciones.
- Desarrollo: bancos G-103, G-111, G-112, G-114, G-114b, G-115 y G-115b. Ya fueron vistos: ningún resultado aquí es reserva nueva.
- Controles: base real con comportamiento estable; rama revisada sin cambios; G-112 y G-115b con la misma educación; desactivación del modelo; guardar/cerrar/recargar en un proceso nuevo; tres semillas de hashes para comprobar reproducibilidad.
- Las cifras automáticas distinguen citas útiles por claves, citas sin dato, abstenciones y excepciones; no sustituyen al juez ciego.

## Criterios y costo

- Correcciones: las nuevas pruebas reproducen el fallo antes del cambio y pasan después; regresión completa sin fallos inesperados; biblioteca inválida deja la memoria exactamente intacta.
- Comparación: informar todos los sistemas, pérdidas y ganancias por turno. Una candidata debe mejorar al menos 3 puntos porcentuales de citas útiles directas/sí-no, sin más citas malas que el control, para solicitar una reserva nueva.
- Latencia: p95 ≤ 5 ms en kiosco; no promover una versión estable si incumple la prueba fija con 100 000 hechos o empeora más del 20 % sin justificación.
- Presupuesto: reconstrucción de nube ≤ 600 s; enseñanza de cada base ≤ 600 s; evaluación ≤ 300 s por comparación; pruebas rápidas ≤ 40 s; regresión completa ≤ 600 s. Registrar CPU, tiempo, memoria y huellas; conservar interrupciones y negativos.
- Si no pasa el desarrollo, las correcciones pueden conservarse, pero la candidata aprendida no reemplaza la base real ni recibe un tag estable.
- Antes de promoción: banco nuevo después de congelar el motor, juez ciego, prueba fija de latencia, tablero y auditoría independiente 5.10.

## En palabras fáciles de entender

Primero se arreglan tres errores: decir que sí cuando una pregunta dice que no, ignorar una frase ya analizada y aceptar archivos incompletos. Después se vuelve a enseñar al programa y se compara con la versión que Leonardo usa, dándoles exactamente el mismo examen. Los exámenes ya conocidos solo sirven para decidir si vale la pena pedir uno nuevo. La versión actual se conserva hasta demostrar que la nueva ayuda más y se equivoca menos.
