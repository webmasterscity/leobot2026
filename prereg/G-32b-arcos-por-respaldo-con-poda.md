# G-32b — respaldo jerárquico de arcos con poda de contextos sin información

Fecha: 2026-09-23. Preregistro previo al cambio. Base: `freeze-G-32` (`5ef2dd5f`), que falló en el control de reinicio: el bot educado ocupaba 112,5 MiB, por encima del límite de carga de 100 MiB. Había 1 828 924 contextos de oportunidad y 1 652 967 de ellos nunca fueron arco.

## Cambio

Al consolidar, se eliminan los contextos de oportunidad que **nunca fueron arco y se vieron ≤2 veces**. Con κ=5, esos contextos solo movían la tasa hacia abajo en ≤30 % respecto del contexto padre.

Exploración en desarrollo visible (300 oraciones de `dev`), que se declara:

| Poda | Contextos | UAS | LAS | F1 de sujeto | Tamaño compacto |
|---|---|---|---|---|---|
| Sin poda | 1 828 924 | 0,7647 | 0,7147 | 0,6159 | 94 MiB |
| Poda ≤2 | 917 302 | 0,7653 | 0,7152 | 0,6132 | 54,7 MiB |

La reserva `test` no se tocó. Aprender más después de consolidar sigue siendo posible, pero los contextos podados empiezan de cero; queda anotado como límite.

## Puerta

La misma de G-32, sin cambios: clases ≥ 0,92; UAS ≥ 0,75 y ≥ +0,01 sobre `freeze-G-31` en la misma reserva; LAS ≥ 0,70; F1 de sujeto y de objeto ≥ 0,60; función con cabeza correcta ≥ 0,85; ≥ 0,02 sobre la ablación; etiquetas barajadas ≤ 0,40; cabezas barajadas ≤ 0,35; fresco sin análisis; **reinicio idéntico**; p95 ≤ 100 ms; educación ≤ 240 s; RSS ≤ 768 MiB; hashseed 0 y 1 idénticos; huella idéntica.

Reserva: 300 oraciones de `test` de ≤60 palabras, con la semilla de `git rev-parse freeze-G-32b:leobot`. Si falla, se registra sin relajarla.

## En palabras fáciles de entender

La mejora anterior funcionaba, pero Leobot guardaba millones de datos inútiles y su memoria ya no cabía en el archivo. Ahora borrará, al ordenar lo aprendido, los datos que casi no dicen nada. En la prueba preliminar eso no cambió la calidad y redujo la memoria casi a la mitad.
