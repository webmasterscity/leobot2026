# E-2 — ¿Sirve localizar evidencia textual antes de inventar significado?

Preregistrado antes de escribir el experimento o cambiar el motor. E-1b halló cero hechos adquiridos en 20 pasajes. Las observaciones crudas actuales retienen parte del texto, pero no ofrecen al usuario un fragmento verificable cuando falla la interpretación. Antes de añadir otra memoria o ruta de diálogo se prueba si una búsqueda textual simple aporta una base suficiente.

## Familia y partición

MLQA español de desarrollo, mismo archivo y SHA-256 de E-1. Excluir los 20 casos del tablero y los 20 de E-1b. Elegir 40 casos ordenados por identificador con semilla `int(sha256((<huella del motor> + ':E-2-piloto').encode()).hexdigest()[:8],16)`. Los pasajes y preguntas son externos. Esta es una prueba de viabilidad de **localización de evidencia**, no de respuesta ni de comprensión y no se usará como reserva final. Si se integra algo al motor, una reserva nueva derivada de la nueva huella será obligatoria.

## Tratamiento y controles

Segmentar con el método actual del motor. Para cada pregunta, ordenar oraciones por coincidencia de tokens normalizados y ponderación IDF calculada solo del pasaje. Comparar con el mismo texto y presupuesto, ordenado por cantidad simple de tokens compartidos. El control sin experiencia no ve pasaje y no puede recuperar evidencia. El control de memoria conserva el pasaje íntegro, pero sin priorización: primera oración y tres primeras. Una oración cuenta como localizada si contiene literalmente alguna respuesta humana normalizada; la respuesta no entra al buscador, solo al evaluador. Registrar top-1, top-3, CPU, RAM y tamaño. Un sistema que solo devuelve una oración permanece clasificado como **memoria/recuperación**, aunque coincida con la respuesta; exact match de respuestas permanece sin resolver. Contradicción, reinicio y revisión de documentos se reservarán para la integración, pues el piloto no conserva estado del bot.

## Decisión y presupuesto

Integrar una interfaz conservadora de evidencia únicamente si el mejor método ubica la respuesta en top-3 de al menos 24/40 casos y supera en al menos 12 casos al control de las tres primeras oraciones. Si IDF no mejora al solapamiento simple en al menos 2/40, usar el método simple. Si ninguno alcanza el umbral, rechazar recuperación como vía principal de E y conservar el resultado negativo. No se ajustarán umbrales tras ver casos. Presupuesto: 40 casos, descarga máxima 80 MiB, 120 s de pared, 60 s CPU. El código del motor permanece congelado en `freeze-E-2-piloto` antes y después. No se añade un subsistema en este piloto. Si posteriormente se integra, debe reutilizar el texto ya conservado o justificar un almacenamiento distinto y no certificar respuestas por parecido léxico.
