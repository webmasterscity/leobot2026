# G-89 — categorías semánticas con el aprendiz de secuencias existente

2026-09-27. Preregistro previo a descarga/implementación. Prueba de educación,
externa a `leobot/`; no cambia respuestas del kiosco ni la base del usuario.

## En palabras fáciles de entender

Saber que una palabra es un nombre no basta para distinguir un lugar de una
persona. Leobot ya aprende clases de palabras a partir de ejemplos; probaremos
si ese mismo método aprende distinciones más útiles con textos marcados por
personas. No escribiremos qué nombres pertenecen a cada grupo ni qué preguntas
debe contestar cada grupo.

Primero debe reconocer nombres y su clase en textos que no usó para aprender,
incluidos nombres nuevos. Si no supera a recordar cada palabra aislada, no
añadiremos esa señal al selector. Incluso si pasa, quedaría por demostrar que
ayuda a responder preguntas de negocios sin inventar y dentro del tiempo pedido.

## Fuentes, restricciones y diferencia

[CoNLL-2002](https://aclanthology.org/W02-2024.pdf) contiene noticias españolas
de EFE de mayo de 2000, con nombres marcados por TALP/UPC y CLiC/UB. Sus cuatro
clases son anotaciones humanas; el código las tratará como símbolos opacos.
Su evaluación exige inicio, fin y clase exactos. El artículo advierte de errores
de anotación que perjudicaron su referencia; no corregirlos a mano para favorecer
este ensayo. No es conocimiento sobre cualquier negocio ni cubre toda semántica.

[TnT, Brants 2000](https://aclanthology.org/A00-1031.pdf) usa conteos de secuencias,
interpolación y terminaciones aprendidas. Ya sustenta `SyntaxMixin` de Leobot:
no se añade otro clasificador. Su evaluación original es de clases gramaticales,
no demuestra esta adaptación a nombres españoles. Las cifras de velocidad de
aquella implementación no se trasladan a Python. Las investigaciones recientes
de 2026 examinadas en G-86/G-88 dependen de redes y no sirven como sustituto.

G-43/G-59 usaban clases gramaticales; PAR-1 agrupó palabras por distribución;
G-83 usó formas de cifras/símbolos. Este ensayo cambia la **educación del mismo
aprendiz de secuencias** por anotaciones semánticas humanas. No introduce listas
de nombres, diccionarios de negocios o correspondencias pregunta→clase escritas
a mano. Si funciona se estudiará reutilizar la representación ya existente de
clases de respuesta, con otro preregistro; no se integra aún.

## Adquisición y partición

Fuente del equipo anotador: [recursos UPC](https://www.cs.upc.edu/~nlp/tools/nerc/nerc.html).
Descargar exclusivamente `https://www.cs.upc.edu/~nlp/tools/nerc/esp.train.gz`
y `https://www.cs.upc.edu/~nlp/tools/nerc/esp.testa.gz`. Registrar URL, fecha,
SHA comprimido/descomprimido, tamaño y costo; commit del manifiesto antes del
aprendiz. Máximo 30 s por descarga y 10 MiB por archivo. Si falla, registrar
interrupción de fuente, sin reemplazarla silenciosamente. `esp.testb` no se abre.
No instalar NLTK ni descargar modelos neuronales. Ignorar columnas POS añadidas
por UPC: usar primera columna (palabra) y última (marca de entidad).

Toda enseñanza usa `esp.train`. `esp.testa` se lee solo después de congelar el
prototipo para comprobar una vez, sin ajustar parámetros. Es desarrollo público,
no nueva reserva del kiosco. Líneas vacías delimitan secuencias; conservar todos
los tokens y secuencias, sin cortes de longitud. Verificar formato BIO declarado
por la fuente; no corregir etiquetas incompatibles en los datos.

## Aprendiz y controles

Extraer del código congelado de `SyntaxMixin.observe_parsed_sentence` únicamente
el bloque genérico que cuenta clases, transiciones, palabras y frecuencias.
Verificar paridad de esos contadores con el método original en prueba focal.
No proporcionar cabezas sintácticas inventadas al aprendiz: los datos no las
anotan. Usar `_empty_syntax`, `consolidate_syntax` y `tag_words` existentes, con
sus parámetros sin modificar y un estado separado. Guardar solo conteos/modelo.

Comparar tres modelos: secuencia aprendida; palabra aislada con su etiqueta más
frecuente (sin observación, etiqueta global mayoritaria); secuencia aprendida
con las series de etiquetas reasignadas entre frases de igual longitud, semilla 1.
El último conserva frecuencias y estructura de marcas; rompe el vínculo con las
palabras. No reentrenar más semillas si el aprendizaje por conteos es invariante
al orden; comprobar serialización/hashseed 1.

Métricas en `testa`: precisión, recuperación y F1 de tramos/clases exactos;
exactitud de tokens, por clase y para entidades cuyo texto normalizado completo
no existe entre entidades de TRAIN. Este último no garantiza que todas sus
palabras sean nuevas: informar también entidades con algún token nunca visto.
No contar el dominio de noticias como transferencia a negocios.

Puerta: F1 de tramos ≥0,65, ventaja ≥0,05 absoluta sobre palabra aislada y
≥0,10 sobre señal confundida; recuperación ≥0,40 en nombres completos no vistos,
con ≥100 ejemplos de ese estrato. Reinicio conserva etiquetas exactas.
Si falla, no enseñar preguntas con ese modelo ni añadirlo a `Bot.answer`.
Renombrado de clases se comprueba en focal sin etiquetas semánticas literales;
no afirmar invariancia al sustituir todas las palabras de una lengua.

## Presupuesto y salida

Adquisición ≤60 s pared; enseñanza ≤60 s CPU; evaluación/controles/recarga ≤120 s;
total ≤180 s CPU, ≤300 s pared excluida adquisición, RAM ≤512 MiB conjunta.
Un proceso pesado; puntos de recuperación tras ajuste, tiempos por fase y por
secuencia, p50/p95/máximo. Esta pieza iría al preparar contexto, no a cada pregunta;
la velocidad de `Bot.answer` se mediría en otro ensayo si pasa, sin prometer 5 ms aquí.
Pruebas focales y trece rápidas; tag `freeze-G89-prototipo` antes de leer `testa`.
Resultado `results_v3/g89_semantic_categories.json`. Motor/base estables intactos,
sin reserva PAR-6, juez/auditor nuevos ni promoción por acertar estas etiquetas.
