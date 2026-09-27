# G-87 — alcance de propuestas aprendidas fuera de las seis iniciales

2026-09-27. Diagnóstico externo anterior a código. Motor/base sin cambios.

## En palabras fáciles de entender

Leobot puede dejar fuera una respuesta antes de examinarla con cuidado. Vamos
a contar cuántas respuestas correctas recuperarían las asociaciones de palabras
que ya aprendió, proponiendo otros textos. También comprobaremos si bastaría
con mirar más candidatos de la lista actual. Conocer la respuesta correcta
permite medir ese límite, pero no significa que Leobot sepa elegirla. Este
diagnóstico no produce respuestas nuevas ni enseña con las soluciones.

## Decisión e hipótesis

G-84 obtiene 482/816 elecciones correctas, aunque la representación aprendida
se calcula sobre todas las unidades. Solo permite elegir entre seis propuestas
iniciales de G-78. G-65 variaba una mezcla escalar y G-66 preferencias léxicas;
G-79/G-84 añadieron un selector que aquellos ensayos no usaban. Antes de cambiar
esa frontera, comprobar si ofrece información realmente distinta de ampliar
la misma lista. No se añade un subsistema por una suposición.

Los antecedentes de alineación y su coste están en G-84, incluido
[Fried y otros, 2015](https://aclanthology.org/Q15-1015.pdf); no es un algoritmo
bibliográfico nuevo ni repite su prueba. Este ensayo reutiliza las probabilidades
aprendidas, sin redes, reglas de negocios ni otro corpus. La investigación
reciente consultada no convierte las cotas de un evaluador en aprendizaje.

## Comparación congelada

Modelo G-84 directo de `.leobot-data/g84_models.json`, SHA
`fd528ab70a602289c271916835c00c570e21b7b2d5ca0f08207515f2bf0384b7`.
Código PAR-2 inmutable cargado con `Components`, preparación de alineación
G-84 y ejecución G-85 directa. Verificar `Bot.answer`: 327/816 útiles, 73/488
citas sin dato y SHA de respuestas G-84 directo exacto antes del diagnóstico.

Sobre los bancos DEV gastados G-62/G-63/G-64, contar disponibilidad de una unidad
que contenga todas las claves de una pregunta directa o sí/no:

1. seis primeras de `_scored` sin modificar;
2. doce primeras de la misma lista;
3. unión de las seis iniciales y las seis primeras por puntaje G-65 directo,
   calculado con las tablas G-84 ya compiladas, desempate por índice de unidad;
4. todas las unidades elegibles, como cota descriptiva.

Las propuestas adicionales excluyen preguntas y encabezados, igual que G-82.
Las seis iniciales permanecen idénticas. La unión tiene entre seis y doce
candidatas (o menos si no hay suficientes unidades), sin completar duplicados.
Conservar inventarios por identificador/unidad, sin copiar preguntas o respuestas
en tablas operacionales. En preguntas sin dato contar tamaños, no inventar una
etiqueta positiva. No reconstruir ni recortar los textos para mejorar la cota.

El evaluador usa claves exclusivamente para contabilizar. No se cambian el
selector, la confianza ni la respuesta pública. Medir cuántas preguntas nuevas
recupera la unión respecto a seis, y cuántas recupera que doce de la misma lista
todavía pierden; pérdidas respecto a doce y duplicados también se registran.

Puerta para justificar un experimento de selección posterior: ≥17 preguntas
adicionales respecto a seis **y** ≥17 cubiertas por unión y no por doce.
Si falla, no construir otro selector para esta propuesta. Si pasa, requiere
nuevo preregistro de aprendizaje y costo: la disponibilidad no acredita utilidad,
prudencia, velocidad ni el objetivo del 60 %. Reserva ajena PAR-6 cerrada.

## Costo y comprobaciones

CPU ≤60 s, pared ≤90 s, RAM ≤768 MiB; sin entrenamiento ni nuevas descargas.
Preparación de documentos, comprobación pública y diagnóstico por separado.
Prueba focal: unión conserva el primer conjunto, no repite unidades ni añade
preguntas/encabezados como nuevas propuestas. Trece rápidas del motor en este
ciclo. Huellas antes/después, commit previo y tag `freeze-G87-diagnostico`.
Resultado `results_v3/g87_proposal_coverage.json`. Sin promoción o auditor 5.10
por este ciclo ordinario; no es refutación de la fase G.
