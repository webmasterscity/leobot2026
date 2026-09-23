# E-6b — Compresión solo cuando los argumentos dejan de ser atómicos

E-6 se retiró antes de reserva: su fórmula rechazó tres pruebas existentes de una relación corta con argumentos de dos palabras. Este preregistro precede a otro cambio de motor; E-6 conserva su fallo. No se modifica ninguna prueba ni el resultado previo.

## Cambio frente a E-6

Conservar exactamente la ganancia de E-6, pero aplicarla como filtro `>1` **solo si algún argumento de apoyo supera cuatro tokens**. Cuando todos los argumentos son de hasta cuatro tokens, mantener el ranking anterior por apoyos. La longitud de argumento es un indicador general de que una plantilla absorbió varias cláusulas; no depende de palabras, dominios o preguntas. Un candidato mixto con algún argumento largo debe pasar el filtro. La ablación apaga todo el filtro y usa el ranking antiguo. La fórmula y el umbral quedan fijados ahora, antes de ver la reserva.

## Pruebas y decisión

Primero, las pruebas rápidas de estado y las pruebas focales de inducción cruda, incluido `tests.test_v45`, deben pasar. Después, congelar código y seleccionar artículos MLQA de desarrollo no usados en tablero/E-1b/E-2/E-3/E-5 con semilla de `sha256((<huella> + ':E-6b').encode())`; 30 artículos para enseñanza y 20 distintos para prueba. Usar los mismos controles y métricas de E-6: tratamiento, ablación con igual texto, barajado, bot fresco, reinicio, cobertura de respuesta en argumentos y CPU. Exigir al menos 50 % menos promociones del tratamiento que de la ablación en texto barajado, cobertura real no inferior a la ablación y cero regresiones en la suite completa antes de promover. Si tampoco aparece ninguna respuesta en un argumento ≤8 tokens, solo se puede registrar cautela, no mejora de lectura. Contraevidencia sobre promociones presentes se registra; la variante no cierra E si sigue activa una afirmación refutada.

Presupuesto: 30+20 artículos por brazo, 80 MiB descarga, 120 s CPU, 180 s pared. Motor idéntico antes y después. Si falla una puerta, retirar la variante y conservar evidencia.
