# G-94 — enseñar con respuestas de negocio competidoras

2026-09-27. Antes de código o medición.

## En palabras fáciles de entender

Añadir clases de palabras no mejoró la elección de respuestas. Ahora probaremos
otra forma de practicar: mostrar una pregunta real de un sitio web, su respuesta
publicada y otras respuestas del mismo sitio que se le parecen. El programa
deberá aprender a elegir la propia. Compararemos esos ejercicios difíciles con
otros elegidos al azar. Una respuesta publicada para otra pregunta podría servir
también para esta, por lo que esas etiquetas son imperfectas. La prueba con
negocios distintos deberá mostrar si realmente ayuda y si conserva la prudencia.

## Motivo y fuentes

G-85 agregó oraciones de enciclopedia con tramos humanos; empeoró. G-93 agregó
clases a los mismos rasgos y no cambió la elección correcta. PAR-5 cambió el
objetivo del aprendizaje con los mismos bancos sintéticos: también empeoró.
G-66 corrigió asociaciones de palabras con rivales aleatorios, sin enseñar el
selector actual. Aquí se conserva ese selector y se cambia **su experiencia**:
preguntas publicadas y respuestas cortas completas del mismo sitio. No se
selecciona una frase de una respuesta larga como en el fallido G-67.

[MFAQ, 2021](https://aclanthology.org/2021.mrqa-1.1.pdf) conserva parejas publicadas
en sitios, con duplicados y desigualdad entre temas. Su modelo neuronal no se usa.
[WebFAQ 2.0, versión 1 del 19-02-2026](https://arxiv.org/html/2602.17327v1)
señala que los textos competidores pueden estar mal etiquetados y que elegirlos
por dificultad no siempre supera a elegirlos al azar. Sus resultados usan redes
y valoración de pares con modelos neuronales; tampoco se importan sus etiquetas,
datos, parámetros ni ganancias. Motiva exigir control aleatorio y declarar ruido,
no suponer que «más difícil» significa «mejor».

La investigación también revisó [PPDB 2013](https://aclanthology.org/N13-1092.pdf)
y [búsqueda simbólica de árboles de 2026](https://aclanthology.org/2026.slide-1.5.pdf).
PPDB contiene asociaciones ruidosas y su dominio histórico ya sirve una página
ajena al proyecto (comprobado el 27-09); no se descargó corpus desde allí. El
segundo trabajo compara árboles ya analizados, no demuestra lectura ni QA.
Ninguno justifica añadir ahora otro sistema de representación.

## Enseñanza preregistrada

Base estable, G-84 directo y referencias PAR-2 idénticos, con huellas verificadas.
Sin G-91 ni G-93. MFAQ TRAIN ya usado, SHA
`c985eb099bcdadf87baa778786148e4de6c9a84057e68b4268ea2f832b884c66`.
Reusar `g65.examples(raw=True)`: máximo 100 pares por dominio, semilla 57,
exclusiones de dominios y deduplicación existentes. No es corpus nuevo.

1. Ordenar los pares por SHA de `(dominio, pregunta, respuesta)` y tomar como
   máximo 8 000 para limitar costo. Antes de preparar unidades, excluir respuestas
   con más de 64 palabras separadas por espacios. No acortar ni resumir.
2. Con el separador actual, conservar solo respuestas que producen exactamente
   una unidad no vacía, que no sea pregunta ni encabezado. Su texto normalizado
   por `g57.plain` debe ser igual a toda la respuesta original. Conservar esa
   respuesta completa. Registrar todo lo excluido.
3. Agrupar por dominio. Excluir preguntas normalizadas asociadas a más de una
   respuesta distinta. Para cada pregunta, rivales posibles: respuestas distintas
   del mismo dominio, sin que el texto normalizado de una contenga el de la otra
   como secuencia completa de palabras. Deduplicar textos de respuesta. Requerir
   cinco rivales posibles; no inferir que por ello son falsos semánticamente.
4. Tomar hasta 4 000 preguntas elegibles por el mismo SHA. Dos ejercicios por
   pregunta: respuesta propia más cinco rivales difíciles; propia más cinco al
   azar. Difíciles: cinco mayores puntajes del recuperador existente `_scored`,
   calculados en el conjunto completo de respuestas elegibles del dominio;
   desempate por texto. Completar rivales que no proponga por SHA, sin tocar
   la respuesta positiva. Aleatorios: ordenar rivales por SHA de pregunta/rival.
5. Cada ejercicio es un documento de seis respuestas completas, separadas por
   saltos de línea y ordenadas por SHA del texto, sin títulos ni preguntas añadidos.
   Cargar por `Bot.load_context`. Si el separador cambia una respuesta o no deja
   exactamente las seis unidades esperadas, excluir el par de ejercicios.
6. Reusar las seis propuestas y 33 variables actuales. Etiqueta positiva solo
   para el texto completo de la respuesta propia; las otras son negativas débiles.
   Exigir que las candidatas tengan positiva y negativa; excluir ambos ejercicios
   si uno carece de ellas. Guardar solo variables/etiquetas para aprender, no
   preguntas ni respuestas operacionales. Contar cuánto difieren ambos ejercicios.

Puerta de disponibilidad antes de ajustar: ≥1 000 preguntas elegibles compartidas
en ≥50 dominios. Si falla, registrar y no ampliar muestra, longitud o presupuesto.
No usar las palabras ni preguntas del usuario para buscar ejemplos.

## Comparación

Cuatro variantes: sin ejemplos adicionales; ejemplos aleatorios; difíciles
(principal); difíciles con etiquetas permutadas por `shuffled_labels` existente,
semilla 1. Mismas preguntas entre dos formas; registrar exclusiones compartidas.
Reusar `g85.teach`: los ejemplos humanos entran en cada ajuste, nunca en la
calibración. Los seis bancos TRAIN/3 520 turnos mantienen mitades por negocio,
regularización L2=1, hasta 25 iteraciones, tolerancia 1e-6, calibración isotónica
con empates G-68 y cita desde 0,4. No cambiar propuesta, rasgos ni umbrales.
Guardar los cuatro modelos antes de consultar DEV.

DEV G-62/63/64 está gastado. Puertas: principal ≥368/816 útiles, ≤73/488 citas
sin dato, ≥491/816 elecciones correctas, ≥17 útiles sobre cada control aleatorio
y confundido, cero citas no literales, p95 y máximo <5 ms. Recuperar huellas
exactas de base y G-84 directo, desactivar y recargar base completa compacta
en proceso nuevo/hashseed 1. La meta final continúa siendo ≥60 % útil con juez
independiente y reserva nueva; este ensayo no la sustituye.

Presupuesto: preparación/enseñanza ≤600 s CPU, evaluación/guardado/recarga ≤200,
total ≤800; ≤1 000 s pared, RAM conjunta ≤1 GiB, un proceso pesado. Registrar
costos previos de modelos reutilizados y todos los abandonos. No nueva adquisición.
Focales: exclusión de respuestas duplicadas/contenidas, permutación de orden y
etiquetado por identidad, descarte si la separación cambia el texto; trece rápidas.
Congelar `freeze-G94-prototipo` antes de ejecutar. PAR-6 y duxiV2 cerrados;
motor y base del usuario intactos. Si falla, no aumentar ejemplos como rescate.
