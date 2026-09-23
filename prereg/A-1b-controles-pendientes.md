# Preregistro A-1b: controles que A-1 no midió por completo

Fecha: 2026-09-22. El motor sigue congelado en `freeze-A-1` con árbol `644c55528a5fd97a8822f719f70e11cfae242783`. No se cambian umbrales ni datos de A-1. El resultado A-1 permanece en `results_v3/a1_meta_abstraction.json`.

## Razón y decisión

A-1 obtuvo 160/160 frente a 80/160 en tres órdenes, pero su evaluador guardó y cargó antes de la contraevidencia, no después. Tampoco entrenó una tarea incompatible ni separó el costo de comprobación, guardado y consulta. Esta validación completa esos controles sin tocar el motor. Si falla, A-1 no supera la fase y se conserva la variante como intento fallido.

## Datos y reserva

Se mantienen las dos familias fuente y la tarea profunda de A-1. La nueva reserva de 160 casos por orden se crea después de este preregistro con semilla `int(644c5552, 16) XOR 0xA1B0`, más los desplazamientos 0, 1 y 2. No se mira antes de ejecutar. Las órdenes son 17, 53 y 97. La tarea incompatible usa los mismos ocho rasgos y 64 experiencias, pero una decisión por mayoría de las cuatro comparaciones; no es la partición de A-1.

## Controles y criterios

- Tratamiento y control sin contraevidencia: ambos parten del mismo aprendizaje; uno recibe 32 observaciones contrarias sobre una fuente, el otro no. Se guarda, se cierra y se recarga cada uno. El primero debe perder la pieza y la vista dependiente; el segundo debe conservar al menos 90 % de aciertos. El primero no debe seguir presentando la regla retirada como segura.
- Incompatible: con las mismas fuentes y 64 experiencias de la nueva tarea, la pieza anterior no debe promoverse como explicación suficiente ni producir errores seguros en la reserva. Si aprende por otro mecanismo, se registra aparte.
- Señal confundida: dos casos realizables con el mismo contenido causal y la pista auxiliar alineada o invertida se ofrecen sin resultado. Se registra qué puede proponer el controlador. El entorno ejecuta el caso invertido y entrega el resultado real mediante `observe`. La decisión posterior debe mantener al menos 90 % de aciertos y cero errores seguros en la reserva invertida. Si el controlador no propone una prueba porque no conserva hipótesis alternativas, se registra como límite, aunque acierte.
- Contabilidad: medir CPU y tiempo de adquisición de fuentes, adquisición de la tarea, búsqueda, comprobación de reserva, intervención, guardado/carga e inferencia; ejemplos, candidatos de pieza y RAM pico. Las mediciones anidadas se marcan como tales y no se suman dos veces. Medir el costo inicial y el de reutilización.
- La huella `freeze-A-1:leobot` y el árbol de trabajo deben seguir idénticos antes y después. Se repite con las tres órdenes y nombres de estrategias distintos en una de ellas.

Presupuesto por orden: 32 experiencias por fuente, 64 por tarea, 160 reservadas; 30 s de CPU por variante, máximo 32 aplicaciones candidatas, 256 MiB de RAM y `timeout 180s` para todo el ensayo. No se cambian estos umbrales después de ver los datos. El evaluador vive fuera de `leobot/` y no será editado tras la primera ejecución de reserva; cualquier corrección metodológica exige otro preregistro.
