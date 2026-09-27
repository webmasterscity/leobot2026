# G-82 · Alcance máximo de las formas ya aprendidas

2026-09-27. Antes del evaluador. Diagnóstico sobre desarrollo gastado; no aprendiz.

## En palabras fáciles de entender

Otra prueba aprendió que ciertas preguntas suelen ir acompañadas de determinadas
formas de cifras o signos en la respuesta. Antes de combinar esa enseñanza con
el selector, contaremos cuántas respuestas adicionales podría ayudar a encontrar
en el mejor caso imaginable. Supondremos que siempre elige bien cuando aparece
esa pista y que nunca estropea un acierto anterior. Es un límite muy favorable,
no una capacidad real. Si aun así el aporte es pequeño, se descarta esa combinación.

## Procedencia fija

Base y G-79 como G-80, sin cambios. Tablas PAR-1 leídas de la otra carpeta,
copiadas de forma independiente a `.leobot-data/g82/par1_tablas.json` y verificadas:
SHA `a5cdbb700dc51660cee7005cf3e6d5e2e773ac695fa1ff49baa1d5dbf1ff68c0`,
234 990 bytes. Educación declarada: 33 787 pares MFAQ de 1 118 dominios TRAIN.
Usar solo las asociaciones `bridge_forms` cuyo destino empiece por `#` (78
asociaciones), excluyendo clases y reglas de terminación.

Reutilizar `chunk_form` desde el objeto git `87c3e8fb1822c6a7dc61990ca3494dc8d509accf`
(`freeze-PAR-1b`), SHA de `leobot/context.py`
`712f4da24427ddc8603f057ec732f732139347573b66d93c978a52502b42c6ae`.
No ejecutar ni cambiar el worktree paralelo; su nueva reserva queda cerrada.

## Conteo y puerta

Reproducir G-79 con Bot.answer: 326/816 útiles y 90/488 citas sin dato, SHA exacto.
En los mismos turnos, extraer términos con el motor estable y formas propias de
cada unidad con la función congelada. Una unidad tiene señal si una asociación
aprendida enlaza algún término de la pregunta con una forma presente en ella.

Para cada pregunta directa/sí-no que G-79 no resolvió útilmente, sumar como aporte
optimista una si **alguna** unidad no interrogativa ni encabezado contiene todas
las claves y tiene señal. Contar también el subconjunto dentro de las seis
candidatas originales y el subconjunto donde la forma distingue unidades.
Conservar siempre los 326 aciertos base. No usar claves dentro de un respondedor.

Registrar activación en preguntas sin dato: una pista de forma no prueba que el
dato pedido exista. La cota no descuenta esos errores y puede ser muy optimista.
Solo autoriza preregistrar una combinación si el aporte máximo es ≥41/816;
para justificarla por sí sola hacia el 60 %, la cota tendría que llegar a 490.
No ampliar asociaciones, fuente, umbral ni selección de preguntas tras ver cifras.

Presupuesto: ≤60 s CPU, ≤90 s transcurridos, ≤768 MiB RAM. Congelar
`freeze-G82-diagnostico` antes de medir. Base y motor intactos. Registrar costos,
huellas y resultado; una puerta de alcance superada no autoriza promoción.
