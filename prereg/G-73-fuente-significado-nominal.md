# G-73 — viabilidad de educación sobre relaciones nominales

2026-09-27, antes de descargar/contar los datos. Motor intacto:
`11a1ef5836382d81a643cad0b217a8669ce0f2d1`. Solo se examina una fuente;
no se entrena ni se modifica el motor y no se miden respuestas.

## En palabras fáciles de entender

Una acción puede expresarse mediante un verbo o un sustantivo. Además, una
frase puede mencionar algo que se explicó en otra. Los dos ensayos anteriores
no aprendieron esas relaciones. Encontramos datos en español cuyos autores
dicen que contienen esa información, revisada por personas. Vamos a comprobar
que los archivos realmente la contienen y que puede recuperarse sin inventar
etiquetas. Si la fuente sirve, todavía habrá que diseñar y probar un aprendiz;
descargarla no hará más inteligente a Leobot.

## Hipótesis y fundamento

[QANom 2020](https://aclanthology.org/2020.coling-main.274/) orientó la búsqueda
de vínculos entre expresiones nominales y verbales, pero su recurso es inglés
y su sistema neuronal/heurístico no es adoptable. La fuente española
[AnCora-Nom](https://aclanthology.org/J12-4005/) describe 23 431 ocurrencias
nominales revisadas manualmente. [IARG-AnCora](https://clic.ub.edu/corpus/en/iargancora)
añade participantes implícitos y revisión humana de una anotación automática.
No todo el recurso se produjo manualmente desde cero.

G-23–G-25/G-71/G-72 solo consumen la conversión UP/UD y tres códigos A0/A1/A2.
No usan la vinculación nominal-verbal ni los participantes implícitos de esta
edición original. Comprobar primero lo que contiene evita añadir otro mecanismo
basado en una descripción bibliográfica. No se necesita subsistema operacional;
el lector XML es una herramienta externa de inspección.

## Fuentes fijadas

Enlaces obtenidos de la [página de los autores](https://clic.ub.edu/corpus/en/ancora-descarregues):

- `https://clic.ub.edu/corpus/system/files/2022-01/ancora-3.0.1es_1.zip`.
- `https://clic.ub.edu/corpus/system/files/2022-01/ancoralex-es-2.0.3.zip`.

Registrar dirección final, bytes, SHA256 y licencia declarada dentro del archivo.
El certificado del servidor no valida con el almacén local y la herramienta web
no abre la página; su contenido público se pudo leer con una excepción limitada
a esa lectura. Si las descargas requieren lo mismo, registrarlo expresamente:
su SHA fija reproducibilidad, no certifica autenticidad editorial. No modificar
la configuración del equipo, no ejecutar contenido descargado ni usar servicios
neuronales. La aceptación como fuente autenticada queda pendiente si no hay
otra comprobación independiente de integridad.

## Conteo y puerta de viabilidad

Abrir los archivos dentro del ZIP, de uno en uno, sin extraer rutas al sistema.
Leer XML con biblioteca estándar, sin resolver entidades externas. Registrar
número de documentos y archivos, errores, etiquetas/atributos presentes y
relaciones explícitamente anotadas. No deducir roles por listas de palabras.

Del léxico contar entradas nominales/verbales, sentidos nominales con verbo
de origen indicado y argumentos/papeles declarados; del corpus contar las
anotaciones nominales, participantes explícitos e implícitos y atributos que
identifiquen sus enlaces. La adaptación a los nombres del esquema es lectura
del formato, no una regla para interpretar español. Primero imprimir solo un
esquema de etiquetas/atributos; fijar su correspondencia antes del conteo total.

Puerta de contenido: ≥200 lemas nominales vinculados explícitamente a verbos;
≥1 000 ocurrencias nominales anotadas en el corpus; ≥3 papeles presentes en
≥50 entradas nominales cada uno; XML utilizable en ≥99 % de archivos de datos.
Contar aparte si hay preguntas humanas alineadas; no darlo por supuesto.
El acceso e integridad deben declararse separados de esta puerta de contenido.

Solo contar información identificable en el esquema. Un campo no comprendido
queda «no verificado», sin sustituirlo por aproximaciones. No hay tratamiento,
ablación ni ganancia de inteligencia en esta inspección. No es reserva: el
corpus es público y se examina para educación/desarrollo. Antes de aprender se
necesitarán partición por documento, objetivos, controles y presupuesto propios;
no copiar en el motor tablas de respuestas ni reglas hechas por los anotadores.

## Recursos y ejecución

Cada descarga ≤64 MiB, máximo dos intentos, ≤120 s transcurridos cada una.
Archivos expandidos sumados ≤512 MiB, cada XML ≤5 MiB, ≤20 000 entradas ZIP.
Inspección ≤120 s CPU, ≤512 MiB RAM, ≤5 minutos transcurridos. Medir descarga y
conteo por separado, anotar interrupciones y huellas antes/después. Caché en
`.leobot-data/`; informe de cifras en `results_v3/`. Commit de este registro
antes del lector y congelación del lector antes de contar el corpus completo.

Resultado permitido: fuente disponible/contenido suficiente, contenido
insuficiente, formato no verificado o acceso pendiente. Ninguno cambia el
35,9 %, resuelve la panadería ni cierra la fase G.

## Resultado de acceso

Ambos enlaces oficiales respondieron HTTP 403 después del fallo de verificación
TLS local. Dos intentos por archivo, sin más reintentos. No se descargaron ZIP
ni se inspeccionó XML. La puerta de contenido queda **sin evaluar**, no fallida.
El primer lector no guardó el fallo antes de salir: se reconstruyó ese registro
desde la traza y se declaró su costo no instrumentado. La segunda descarga
fallida sí quedó medida: 0,024 s CPU y 1,021 s transcurridos.
Ver [registro de acceso](../results_v3/g73_access.json).

Se identificó otra fuente primaria, [Predicate Matrix 1.3](https://adimen.ehu.eus/web/PredicateMatrix),
con correspondencias de AnCora-Nom. Se examinará bajo G-73b con un criterio de
contenido propio: no se sustituirá silenciosamente por el corpus solicitado
ni se tratarán sus correspondencias como frases anotadas o preguntas humanas.
