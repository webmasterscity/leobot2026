# G-31 — funciones de dependencia aprendidas por conteo

Fecha: 2026-09-23. Preregistro previo al código. Base: `estable-G-3` (`3b13f49b`), con la sintaxis de G-29: clases 97,2 % y UAS 0,743, sin etiquetas de función.

## Por qué

G-30 mostró que usar la estructura solo para elegir tramos empeora la lectura. La vía que una persona usa, y que encaja con Leobot (hechos, consultas, reglas, razonamiento), es convertir cada oración en hechos de la forma «quién hace qué a quién». La pregunta se convierte en la consulta correspondiente.

Para eso hace falta saber la **función** de cada dependencia (sujeto, objeto, complemento, modificador), no solo de quién depende. Hoy el motor no la aprende.

## Hipótesis y alternativa

La etiqueta UD de cada arco se puede estimar solo por conteo a partir de rasgos de configuración, con respaldo de lo específico a lo general:
- (clase de cabeza, clase de dependiente, dirección, distancia agrupada);
- versiones léxicas de la palabra dependiente y de la cabeza vistas ≥3 veces;
- la primera palabra dependiente de tipo `case` o `mark` del dependiente (por ejemplo «a», «de», «que»).

Esa estimación da una asignación suficiente para extraer sujeto y objeto. Alternativa: sin un modelo discriminativo, la precisión de etiquetas queda baja para funciones clave (`nsubj`, `obj`, `obl`).

## Mecanismo (5.8)

- **Fallo que resuelve:** el motor no sabe qué papel cumple cada palabra en la oración.
- **Por qué no bastan los actuales:** G-29 solo produce cabezas; las raíces crudas necesitan superficies repetidas.
- **Qué lo distingue:** ablaciones sin léxico y sin marcador, y etiquetas barajadas.
- **Qué eliminaría si la extracción posterior funciona:** los rasgos de vecindad lineal de G-28b que queden redundantes.

Interfaz: `observe_parsed_sentence(palabras, clases, cabezas, funciones=None)` acepta las funciones cuando la demostración las trae. `parse_words` devuelve `labels` cuando hay modelo de funciones. La etiqueta se elige de forma independiente por arco, con el respaldo lineal suavizado del contexto más específico al más general, sin gradientes.

## Datos, controles y puerta

- **Datos:** los de G-29. UD AnCora `train` para educar; se usa la columna DEPREL y se quita el subtipo tras «:».
- **Desarrollo:** 300 oraciones de `dev`.
- **Reserva:** 300 oraciones de `test` de ≤60 palabras, con los primeros 8 hexadecimales de `git rev-parse freeze-G-31:leobot`.

Se miden:
- **LAS:** cabeza y función correctas.
- **Precisión de etiqueta con la cabeza correcta.**
- **F1 por función** para `nsubj`, `obj`, `obl`, `iobj` y `amod`.
- **Con cabezas y clases del corpus:** diagnóstico, no puerta.

Controles:
- **Etiquetas barajadas:** la educación con funciones permutadas al azar dentro de cada oración.
- **Ablación sin rasgos léxicos ni marcador:** solo las clases.
- **Fresco:** sin `labels`.
- **Reinicio.**
- **Hashseed 0 y 1:** resultados idénticos.

Puerta:

| Criterio | Umbral |
|---|---|
| Clases | ≥ 0,92 |
| UAS | ≥ 0,70 (no retrocede respecto de G-29) |
| LAS | ≥ 0,63 |
| Precisión de etiqueta con cabeza correcta | ≥ 0,85 |
| F1 de `nsubj` y de `obj` | ≥ 0,60 cada uno |
| Ventaja de LAS sobre la ablación sin léxico ni marcador | ≥ 0,02 |
| LAS con etiquetas barajadas | ≤ 0,40 |
| Fresco | sin etiquetas |
| Reinicio | idéntico |
| p95 por oración de ≤40 palabras | ≤ 100 ms |
| Educación | ≤ 240 s de CPU |
| RSS | ≤ 768 MiB |
| Huella | idéntica |

Si falla, se registra sin relajarla.

## En palabras fáciles de entender

Leobot ya sabe de qué palabra depende cada una en una oración. Ahora aprenderá, con los mismos ejemplos marcados por expertos, qué papel cumple cada dependencia: quién hace la acción, qué recibe la acción, dónde o cuándo ocurre. Es el paso previo para que convierta lo que lee en datos del tipo «quién hizo qué», que después puede consultar y usar para razonar.
