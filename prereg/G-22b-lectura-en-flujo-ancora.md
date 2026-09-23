# G-22b — leer AnCora en flujo tras interrupción por tamaño

Fecha: 2026-09-23. G-22 se detuvo **antes de analizar oraciones**: UD declaró 43 100 702 bytes frente al tope de 40 MiB. El motor H0 siguió intacto. No hay resultado lingüístico que modificar ni reinterpretar. Este preregistro antecede al cambio del evaluador.

Se mantienen íntegros [G-22](G-22-fuente-papeles-verbales.md): mismos repositorios y revisiones UP `7a03859143e52c57f94a8c0480c0e6d433f6a91f` / UD `20adddbfcdd773c6dc97ba48ea11ca9364e74185`, solo archivos `train`, las seis condiciones de fuente (≥5000 oraciones pareadas con texto, ≥1000 predicados, ≥5000 argumentos, ≥95 % de IDs de tokens alineados, ≥90 % de argumentos válidos, ≥100 lemas y ≥3 papeles compartidos según umbral), dos hashseeds y H0 congelado. No abrir `dev/test`. Solo contar datos; ningún learner se construye en este ensayo.

Única modificación: permitir hasta **48 MiB** para UD (tamaño comunicado por servidor 43 100 702 bytes) y leerlo por líneas desde la red, acumulando SHA-256 y total de bytes sin retener el archivo completo. UP mantiene 20 MiB. Mantener CPU ≤15 s, pared ≤45 s y RAM pico ≤128 MiB. El lector de oraciones debe producir los mismos campos que G-22; si hay un error de esquema, registrar interrupción y corregir el evaluador con procedencia explícita, sin cambiar condiciones de aceptación. Congelar el evaluador antes de descargar y repetir con `PYTHONHASHSEED=0/1`; conservar ambas huellas de fuente y conteos.

Un pase solo justificaría el siguiente ensayo de aprendizaje de papeles verbales, no una mejora de Leobot. Si falla por recursos o calidad, conservar el motivo y buscar otra fuente o representación.

## En palabras fáciles de entender

El primer intento se detuvo porque el archivo era un poco más grande de lo previsto. Leeremos el mismo archivo por partes, sin guardarlo entero en la memoria. Las condiciones para decidir si la colección sirve siguen exactamente iguales.
