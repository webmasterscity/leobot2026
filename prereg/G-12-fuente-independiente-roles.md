# G-12 — puerta de fuente independiente para roles de texto español

Fecha: 2026-09-23. Preregistro anterior al código de descarga/inventario. Árbol congelado `estable-E-1:leobot` = `1f3187f2ced4c97364503187d074815f33612326`. G-10/11 demostraron pistas de acciones entre bases SQL, pero no composición suficiente. Ajustar más el mismo corpus puede explotar su traducción o sus frecuencias; la siguiente decisión exige otra fuente y otra estructura de significado.

## Fuente y límites

Usar [MASSIVE 1.1 oficial](https://github.com/alexa/massive) de Amazon, licencia CC BY 4.0 según su [ficha oficial](https://huggingface.co/datasets/AmazonScience/massive). Descargar el archivo publicado por Amazon en S3, como máximo 45 MiB, por flujo, leer únicamente `es-ES.jsonl` y analizar solo filas `partition=train`. Registrar SHA-256 de ese miembro, cantidad de bytes, etiquetas y calidad de anotación. No guardar el paquete completo ni copiar el proyecto. Las frases son localizaciones humanas de SLURP en inglés: **no** presentarlas como español independiente ni como documentos crudos. Se excluyen `dev` y `test` oficiales de todo este ciclo.

La tarea futura sería aprender de pares explícitos `utt` ↔ `annot_utt` el vínculo entre un fragmento y su papel; `intent` aporta objetivo. Esas anotaciones son **instrucción**. Esta puerta solo decide si existen papeles reutilizables entre ámbitos y si sus fragmentos se pueden recuperar sin usar el significado. No se enseña todavía a Leobot ni se afirma capacidad nueva.

## Partición y criterio fijo

Contar las filas de enseñanza por `scenario` y los nombres de papel dentro de `annot_utt`; extraer los nombres entre corchetes mediante sintaxis genérica `[papel : texto]`, sin lista escrita de papeles. Comprobar que el texto del fragmento figura literalmente en `utt`, tras comparación Unicode sencilla sin distinguir mayúsculas. Una fila con anotación mal formada queda contabilizada, no corregida a mano. Considerar elegibles los ámbitos con ≥100 frases de enseñanza. Para semillas 719, 787 y 853, barajar ámbitos elegibles con los primeros 8 dígitos de H0 XOR semilla XOR `0x69B` y excluir `max(3, round(0.2*n))` ámbitos completos.

Una etiqueta es reutilizable si aparece en ≥3 ámbitos de enseñanza y en ≥20 frases de enseñanza. La puerta pasa solo si **cada** partición tiene ≥4 ámbitos de comprobación elegibles, ≥10 etiquetas reutilizables en enseñanza, ≥5 de ellas presentes en ≥20 frases de comprobación y en ≥2 ámbitos de comprobación, ≥25 % de frases de comprobación con al menos una etiqueta reutilizable, y ≥98 % de fragmentos anotados recuperables literalmente en `utt`. Además el archivo español debe ser accesible dentro de 45 MiB y 60 s de pared, con RAM ≤256 MiB. Repetir con `PYTHONHASHSEED=0/1` y exigir conteos idénticos.

Si la puerta falla, no escribir un learner para esta fuente. Registrar qué condición falló; buscar otra fuente o un diseño que no presuponga reutilización de etiquetas. Si pasa, preregistrar **otro** ensayo con tratamiento de aprendizaje de fragmentos y papeles, controles barajado dentro de ámbito, solo memoria, fresco, mismo texto sin learner, renombrado de entidades, contraevidencia y reinicio. Las etiquetas de comprobación solo entrarían al evaluador tras la predicción. Una puerta de fuente nunca certifica comprensión, transferencia ni AGI.

Costo: inventario CPU ≤15 s, pared ≤60 s, memoria ≤256 MiB, cero hipótesis de learner y cero respuestas. H0 debe coincidir antes/después. Si falla la red o el tamaño, registrar la interrupción como tal, sin reinterpretarla como fracaso del mecanismo.

## En palabras fáciles de entender

El ensayo anterior usó preguntas sobre bases de datos. Ahora comprobaremos si hay suficientes ejemplos en otro tipo de preguntas para enseñar qué parte del texto nombra una fecha, un lugar u otro papel. Si esos papeles no se repiten entre ámbitos, este material no sirve para probar la transferencia que buscamos.
