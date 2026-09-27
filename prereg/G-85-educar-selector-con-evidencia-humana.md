# G-85 · Enseñar a elegir con evidencia localizada por personas

27 de septiembre de 2026. Preregistro antes del código y del resultado.

## En palabras fáciles de entender

Tenemos preguntas escritas por personas y el lugar exacto del texto donde está
su respuesta. Ya se usaron para enseñar conexiones entre palabras, pero no para
enseñar directamente al selector cuál de varias frases escoger. Probaremos esa
enseñanza con el mismo selector y la misma información de entrada. También lo
enseñaremos con las respuestas señaladas en lugares equivocados, para comprobar
si aprender de la evidencia correcta produce una diferencia real.

## Hipótesis y antecedentes

G-78 usó SQAC para pesos léxicos; PAR-2/G-79/G-84 enseñaron el selector con 3 520
turnos de bancos de negocio gastados. G-84 directo dio 327/816 útiles y 73/488
citas sin dato. El segundo paso no demostró la ventaja fijada: se retira aquí.
La hipótesis nueva es **educación adicional del mismo selector**, con unidades
marcadas por el tramo humano; no otro clasificador ni otra regla lingüística.

Fuente humana: [SQAC oficial](https://huggingface.co/datasets/PlanTL-GOB-ES/SQAC/blob/main/README.md),
solo train, SHA `1d5c76176646e2ae7bdcd8b5ec6f18349102a9363aa25ad7d0e48262d7480d43`.
Es la misma fuente gastada en F-4–F-9 y G-78, **no una reserva ni un corpus nuevo**.
Sus preguntas son de textos enciclopédicos/noticias; la transferencia a negocios
es una hipótesis que puede fallar. Las tablas léxicas G-78 ya vieron esos ejemplos;
no presentar la enseñanza del selector como independiente de esa exposición.

## Representación fija y corrección de costo

Usar exactamente la tabla directa de `.leobot-data/g84_models.json`, SHA
`fd528ab70a602289c271916835c00c570e21b7b2d5ca0f08207515f2bf0384b7`.
Primer paso G-65 truncado/normalizado, ocho destinos;
los dos prefijos de cuatro rasgos reciben la **misma** señal directa, como el
control G-84. Conservar los 25 rasgos PAR-2, K=6 y su puntuación de candidatas.

Se permite calcular una sola vez esos cuatro rasgos repetidos y copiarlos al
segundo prefijo, conservando sus valores. Comprobar paridad de rasgos y SHA
exacto de respuestas con G-84 directo antes de interpretar nuevas cifras. No
suprimir una señal distinta ni guardar respuestas de preguntas. Preparación por
documento instrumentada, como G-84. Esta reducción de trabajo repetido se aplica
por igual al control y a la nueva enseñanza.

## Material humano y etiquetas

Elegir los mismos 10 000 identificadores por SHA que G-78: posición humana válida,
tramo dentro de una oración según `g78.segments/locate`, al menos otra oración
sin el texto de respuesta, exclusión del ejemplo ya publicado en F-4. Conservar
sus filtros y límites, sin seleccionar preguntas por resultado del kiosco.
Guardar SHA de identificadores para comprobar el conjunto, no sus textos en motor.

Cargar cada párrafo mediante Bot.load_context y obtener sus seis candidatas con
el código fijo. Positiva: unidad literal que cubre la posición completa del tramo
humano. Negativa: otra unidad que tampoco contenga el texto normalizado de esa
respuesta; excluir las ambiguas que contienen ese mismo texto sin cubrir el tramo.
Excluir del ajuste preguntas sin una candidata positiva y una negativa. Registrar
exclusiones, cobertura de localización y número de filas; no cambiar segmentación
ni reemplazar preguntas excluidas para mejorar el resultado. No asignar a mano
tipos de respuesta ni significados a palabras.

## Enseñanza, controles y calibración

Los mismos seis bancos TRAIN del selector, mismas mitades SHA por negocio,
L2=1, 25 iteraciones, tolerancia 1e-6; sin cambiar código de `fit` PAR-2.
En cada ajuste de una mitad, añadir todas las filas humanas admisibles una vez,
con el mismo peso por candidata. Los puntos para calibrar la decisión se obtienen
**solo** de la otra mitad de negocios; nunca de las filas humanas añadidas.
Pesos finales con todo TRAIN más material humano, calibración con empates G-68,
cita desde 0,4. No elegir pesos de fuente o umbrales con DEV.

Variantes: control sin enseñanza humana (reproduce G-84 directo), principal con
tramo humano y control con sus etiquetas permutadas dentro de cada pregunta
humana, semilla 1; mismas candidatas y cantidad de positivos. Etiquetas de negocio
sin cambios en todos. Tablas guardadas antes de abrir DEV G-62/63/64 gastado.
Panadería del usuario, duxiV2 y reserva PAR-6 no participan en enseñar o seleccionar.

## Puertas y presupuesto

Principal ≥344/816 útiles, ≤73/488 citas sin dato; ≥499/816 elecciones correctas;
≥17 útiles sobre cada control sin enseñanza/confundido. Ninguna selección sin
abstención equivale al 60 % de respuestas útiles pedido. Literalidad, desactivación,
base completa compacta y recarga en proceso nuevo/hashseed 1; p95 y máximo <5 ms.
No promover sin todas las puertas y posterior revisión/integración/reserva nueva.

Enseñanza/preparación ≤600 s CPU, evaluación/controles ≤200, total ≤800,
RAM conjunta ≤1 GiB, tiempo transcurrido ≤1 000 s; procesos pesados secuenciales.
Guardar candidata compacta como G-84b, sin quitar datos ni superar 100 MiB.
Conservar costos por preparación humana, ajuste, preparación de contexto,
guardado y evaluación. Congelar `freeze-G85-prototipo` antes de medir. Pruebas
focales de localización/ambigüedad, paridad de cálculo repetido, separación de
calibración y persistencia; trece rápidas del proyecto.

## Interrupción de preparación y aclaración previa a corregir

El primer intento comprobó paridad exacta en los 3 520 turnos/20 629 candidatas,
pero se interrumpió antes de ajustar o medir DEV: algunos párrafos con separador
vertical se interpretan como cabecera de tabla y dejan cero unidades. La interfaz
interna de candidatas supone al menos una y lanza IndexError. Se reprodujo en
tres contextos fuente; sus SHA están en el informe de interrupción.

La exclusión ya prevista de preguntas sin candidata positiva incluye unidades
vacías. Comprobar ese caso **antes** de pedir candidatas, contarlo y continuar;
no cambiar segmentación ni la base. Añadir prueba focal del caso y registrar
cualquier excepción de preparación. CPU exacto del intento inicial no capturado:
paridad 19,994 s es solo una cota inferior. Diagnóstico adicional 4,527 s.
Refijar como `freeze-G85-prototipo-b` antes de repetir; mismas puertas y datos.
