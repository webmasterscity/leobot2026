# G-115: δ contrastivo dentro del documento, aprendido de los negocios de enseñanza (solo datos, motor congelado)

- Fecha: 2026-09-29.
- Estado: diseñado. Este preregistro precede al código del experimento y a toda medida.
- Motor: `freeze-G112-1`, huella `d1c92eb7…`. **No se cambia `leobot/`**: solo cambia el dato `context_model['delta']` / `rare_delta` de la base.

## Qué fallo resuelve
Diagnóstico sobre el banco gastado `congelado_g103` (desarrollo, 103 turnos «elige otra» con la unidad correcta entre las 8 candidatas).
- δ(q), el peso de una palabra de la pregunta en la mezcla, se aprendió de SQuAD-es convertido a pares pregunta–respuesta. Así, palabras sin contenido reciben casi el mismo peso que el tema de la pregunta: δ(haber) = 0,50, δ(el) = 0,23, δ(a) = 0,40, δ(estacionamiento) = 0,57.
- Como la ganancia es log(δ/p0 + 1 − δ), una palabra vacía que es rara en el texto gana a la palabra temática.
  - «¿Hay estacionamiento?» elige «requiere **haber** completado…» (ganancia 3,75) antes que «No disponemos de **estacionamiento** propio» (2,98).
  - «¿A qué hora cierran hoy?» elige «máximo 48 **horas**» antes que «Lunes a viernes: 8:00 a.m. - 8:00 p.m.».
- Causa general: δ mide cuánto repite una respuesta la palabra de su pregunta, y no cuánto **distingue** esa palabra a la unidad que responde de las demás unidades del **mismo** documento, que es lo que decide la elección.

## Por qué los mecanismos actuales no bastan
- La contraposición G-59 compara con otra respuesta del mismo dominio de MFAQ, no con las unidades vecinas del documento.
- G-78 usó frases ubicadas de SQAC (Wikipedia): mejoró la elección en desarrollo (440 frente a 420 de 816), pero no los útiles.
- Aquí la estadística se cuenta en la misma clase de documento que el kiosco: los 216 negocios de enseñanza de los 9 bancos antiguos, con la unidad correcta marcada por sus claves.

## Aprendizaje (fijado ahora)
Para cada turno `directa`/`si_no` de enseñanza con claves y con alguna unidad que las contiene («correctas»):
- Q son las formas de diccionario de la pregunta.
- Para cada q de Q se cuentan:
  - n(q) += 1;
  - own(q) += 1 si alguna correcta tiene q (propia o heredada);
  - other(q) += la fracción de las unidades no correctas (sin títulos ni preguntas) que tienen q.
- δ'(q) = max(0, (a − b) / (1 − b)), con a = (own + 1)/(n + 2) y b = (other + 1)/(n + 2). Es la forma de mezcla de G-57.
- Cobertura según n(q):
  - con n(q) ≥ 3: δ'(q) propio;
  - con n(q) < 3: el δ' agrupado de la clase gramatical aprendida (AnCora) más frecuente de la palabra en las preguntas de enseñanza;
  - `rare_delta`: el δ' agrupado de todas las palabras con n entre 1 y 5.
- Palabras del δ antiguo que no aparecen en las preguntas de enseñanza: se conserva su δ antiguo (variante **reemplazo**).
- Variante **media**: (δ antiguo + δ') / 2 para las palabras que tienen los dos.
- Nada más se toca: el puente, los prefijos y la confianza quedan iguales.
- Encima de cada variante se reenseña el modelo denso G-112 (`experiments/g112_educar.py`, semilla 0) con los mismos 216 negocios.

## Selección en desarrollo (bancos gastados: `congelado_g103`, `congelado_g111`, `congelado_g112`, `congelado_g114`, `congelado_g114b`)
Medida automática por claves, igual que `experiments/g111b_evaluar.py`: útiles con a lo sumo 0,26 N / 0,39 N / 0,65 N citas malas, sumados sobre los cinco bancos.
Se elige para la reserva la variante (reemplazo o media, con el modelo G-112 reenseñado) que:
1. mejora a G-112 actual en ≥ +2 puntos de N con 0,39 N y con 0,65 N sumando los cinco bancos;
2. no empeora en más de 1 punto en ninguno de los cinco bancos por separado con 0,39 N.

Si ninguna cumple, G-115 queda **negativo en desarrollo**, se registra y no se pide banco.

## Reserva (si pasa la selección)
- Banco nuevo `congelado_g115`: 8 redactores independientes (Agent con `isolation: "worktree"`, nunca *fork*). Encargo como el de G-114b, con los sectores de `congelado_g114b` añadidos a los excluidos. Commit del banco antes de ejecutar Leobot.
- Juez ciego doble con el encargo de G-114 y la misma herramienta (`experiments/g114_juez.py --coherentes`).
- Comparación: variante elegida frente a G-112 actual.

Umbrales:
1. Útiles de la variante − G-112 ≥ +3,0 puntos de N, con bootstrap por negocio que excluye 0.
2. Engañosas de la variante ≤ G-112 + 0,01 N.
3. Sin respuesta coherentes bien manejadas ≥ 97 %.
4. `Bot.answer` p95 ≤ 5 ms y reinicio idéntico.

Si pasa: se propone como base del kiosco, con regresión completa, latencia, tablero y auditoría 5.10 antes de un tag estable.

## Presupuesto
- Aprendizaje de δ' ≤ 5 min de CPU.
- Cada reenseñanza G-112 ≤ 15 min.
- Evaluación de desarrollo ≤ 20 min.

## Controles
- **Señal confundida:** δ' contado con la unidad correcta sustituida por otra unidad al azar del mismo documento (semilla 0). Debe quedar por debajo del tratamiento.
- **Motor:** la huella es idéntica antes y después.
- **Ablación:** es el sistema G-112 actual (δ antiguo).
