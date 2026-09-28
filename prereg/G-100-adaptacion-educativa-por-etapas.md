# G-100 — adaptar la decisión después de la enseñanza general

2026-09-27. Continuación autorizada del modelo, sin tocar motor/base.

## En palabras fáciles de entender

G-99 aprende mejor a elegir frases en textos generales, pero vuelve a callar
en las preguntas difíciles de los negocios. La mayor parte de sus ejercicios
eran textos generales. Probaremos una etapa final de práctica con negocios de
enseñanza; los negocios de comprobación seguirán separados. Compararemos con
seguir practicando textos generales y con ejemplos de negocio confundidos.
Si no mejora en las preguntas separadas, se conserva como otro resultado negativo.

## Hipótesis y decisiones anteriores al resultado

G-99: 6000 ejercicios humanos generales y 1737 sintéticos de negocios. En
comprobación educativa, elección lexical 919/1534; en abstenciones comunes 19/61,
por debajo de las 22 candidatas originales. Red con vectores completos 10/61,
historial 9/61. Todas las confianzas máximas <0,4. No hay mejora de utilidad.
H1: la mezcla educativa favorece ejercicios distintos de la atención al cliente;
una etapa posterior de adaptación puede mejorar su selección sin cambiar el código.
Es hipótesis, no causa demostrada. La enseñanza por etapas aparece también en
[SmallReason-ColBERT v1](https://arxiv.org/html/2609.29652v1); no se atribuyen sus
resultados al mecanismo pequeño ni se usa su modelo o sus datos.

Reusar exactamente fuentes, particiones y variables G-99, incluido historial.
Pesos iniciales: cada una de las tres decisiones G-99 lexical, interaction,
history. Estandarización congelada desde G-99. Para cada una, tres continuaciones:
- `business`: solo los 1737 ejercicios sintéticos TRAIN de negocios.
- `general`: 1737 ejercicios humanos SQAC TRAIN, primeros por SHA(id), igual costo
  en ejemplos y pasos que business, usando las mismas fuentes excluidas de prueba.
- `shuffled`: mismos negocios, preguntas e historial permutados por grupo,
  documentos y etiquetas intactos.

Veinticuatro épocas adicionales, lotes 64, semilla 1, misma pérdida G-99,
AdamW nuevo 0,0003 y decaimiento 0,001. No más capacidad, datos nuevos ni umbrales
escogidos por resultados. La variante principal es `lexical_business`, escogida
antes de medir por su mejor selección previa; las otras son controles de hipótesis
y de representación. No elegir la variante ganadora retrospectivamente como principal.

Reajustar isotónica solo con los 455 casos de calibración separados de G-99.
Dos puntos de operación, 0,4 y 0,9, ambos con puntaje de unidad >0; principal 0,9.
Comparar utilidad, errores, selección cruda y latencia con estable y G-98 sobre
los mismos 157 turnos gastados; verificar G-99 congelado con sus salidas guardadas.
Reportar comprobación educativa por fuente (negocio/general), no solo mezclada.
Meta ≥62/102 útiles, cero errores nuevos, <5 ms p95 y máximo completo/condicional.
Paso intermedio ≥5 útiles más que G-98 sin errores nuevos. Solo sirve como
desarrollo; si pasa, reserva nueva independiente obligatoria antes de generalizar.

Desactivación, cambio documental, exportación y reinicio en proceso nuevo
hashseed 1. Caso exacto del usuario aparte. Trece rápidas y focales existentes.
No repetir búsquedas de modelos ni editar G-99. Preregistro/commit antes de código;
congelación antes de enseñanza y de evaluación. CPU preparación/enseñanza/confianza
≤900 s y pared ≤1200, evaluación total ≤300 CPU/500 pared, RSS ≤3 GiB, una hebra
y un trabajo pesado a la vez. Costos previos identificados como reutilizados.
Artefactos `.leobot-data/g100/`, resultados `results_v3/g100_*`.
