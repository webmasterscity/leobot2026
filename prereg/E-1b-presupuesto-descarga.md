# E-1b — Reintento del diagnóstico literal

El primer intento E-1 terminó antes de seleccionar preguntas: el archivo MLQA oficial mide 75 719 050 bytes y el límite de descarga preregistrado era 40 MiB. No se vio ningún caso del conjunto seleccionado ni hubo salida del motor.

Se conservan íntegros la familia, la semilla derivada de la huella, la exclusión del tablero, los controles, las métricas, los umbrales y los límites de ejecución de [E-1](E-1-diagnostico-lectura-literal.md). El único cambio es subir el límite de descarga a **80 MiB**. Se etiqueta de nuevo el motor antes de la selección; su árbol debe ser idéntico al de `freeze-E-1`. El resultado no cuenta como cierre de la fase E.
