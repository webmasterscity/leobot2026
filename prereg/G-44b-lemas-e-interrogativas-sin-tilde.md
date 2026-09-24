# G-44b — alinear por lema y reconocer interrogativas sin tilde

Fecha: 2026-09-24. Preregistrado después del desarrollo de [G-44](G-44-el-lector-aprende-como-se-responde.md), que se refutó en desarrollo, y antes de congelar. Base: `freeze-G-43b` (árbol `263cc12b`).

## Por qué

En el desarrollo de G-44, las dos piezas que no dependían de lo aprendido subieron MLQA visible de 0,2168 (G-43b) a 0,2252 sin cambiar la conversación (138 de 186 en los 6 conjuntos gastados). Son dos correcciones de causa general:

1. **Alinear por lema aprendido.** La raíz de 5 letras confunde palabras distintas («bibliotecaria» = «biblioteca») y no une formas de distinto largo. AnCora `train` trae los lemas en el mismo archivo con el que ya se educa la sintaxis.
2. **Interrogativas sin tilde, solo al abrir la pregunta.** «¿Cuantos…?» y «¿Quien…?» se trataban como preguntas de sí o no; en la muestra MLQA de G-43b eso costó −0,009. Se reconocen sin tilde solo en la posición de la que se aprendieron.

G-44b es G-43b más estas dos piezas; nada de lo refutado en G-44 entra. Interruptores de ablación: `lemma_alignment` y `folded_openers`.

5.8:
- **Qué fallo resuelve:** la pérdida de MLQA de G-42 a G-43b (el criterio que falló en G-42 y G-43b) y los choques de raíz en conversación.
- **Por qué no bastan los actuales:** la raíz de 5 letras es una regla de largo, no aprendida.
- **Qué lo distingue:** las ablaciones en MLQA no vista.
- **Qué se elimina:** la raíz de 5 letras en la alineación estructural y en la verificación.

## Evaluación

- **Reserva doble:** dos conjuntos nuevos con el encargo fijo, redactados después de `freeze-G-44b`, validados y unidos (unas 60 preguntas). Se miden G-44b, G-43b congelado, «siempre no lo sé», el subagente sin claves, sin memoria, barajada y renombrado.
- **MLQA no vista:** 600 casos no usados antes (ni en educación, ni en desarrollo, ni en las muestras de G-43 y G-43b), con la semilla de `freeze-G-44b`. Se miden G-44b, la ablación con los dos interruptores apagados y el lector de G-28 solo.

## Puerta (candidata a `estable-G-11`)

| Criterio | Umbral |
|---|---|
| Aciertos en la reserva doble | ≥ 60 % y ≥ G-43b congelado − 1 (no inferior) |
| Sí o no falsos (sin abstenciones) | ≤ 2 |
| Respuestas abiertas equivocadas | ≤ 20 % de las preguntas abiertas |
| Memoria barajada | 0 aciertos en abiertas y sí/no |
| Renombrado: respuestas invariantes | ≥ 90 % |
| MLQA no vista (600) | F1 ≥ lector de G-28 solo − 0,005 |
| Aporte en MLQA no vista: G-44b − ablación | ≥ +0,005 F1 |
| Regresión completa | sin fallos nuevos |
| Latencia fija intercalada con `estable-G-10` | ≤ +20 % y dentro de presupuestos |
| Respuesta en conversación | p95 ≤ 200 ms |
| Verificación independiente 5.10 | cifras reproducidas, sin hardcodeo ni filtraciones |

Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Leobot reconocía las palabras por sus primeras cinco letras y confundía «bibliotecaria» con «biblioteca». Ahora las reconocerá por su forma de diccionario, que aprende del mismo libro con el que aprendió gramática. Y si alguien escribe «¿Cuantos…?» sin tilde, entenderá igual que es una pregunta. Son dos arreglos pequeños, pero afectan a todo lo que Leobot lee.
