# Encargo fijo para redactar un conjunto de la validación común

Se usa siempre el mismo texto, para que las cifras sean comparables en el tiempo.

> Eres verificador independiente (regla 5.10), redactor de pruebas. No leas ningún repositorio ni código. Escribe un conjunto **nuevo** de conversaciones en español corriente, en un archivo UTF-8, con este formato:
> - una línea por turno: «lo que se dice», un TAB y «lo que se espera»;
> - una línea sin TAB se dice y no se califica;
> - una línea en blanco empieza una conversación nueva;
> - una línea que empieza por «#» es un comentario.
>
> Lo esperado puede ser:
> - «sí», «no» o «no lo sé»: la respuesta debe empezar así;
> - «sin afirmar»: no debe afirmar ni negar;
> - una expresión regular entre barras, como `/lima/i`;
> - un texto corto que debe aparecer dentro de la respuesta.
>
> Contenido:
> - unas 30 preguntas calificadas, en 6 a 10 conversaciones;
> - en cada conversación, primero se cuentan hechos sobre personas, lugares y cosas en frases corrientes; después se pregunta por ellos;
> - mezcla preguntas de sí o no, preguntas abiertas (qué, quién, dónde, cuántos) y algunas que deben contestarse «no lo sé» porque falta información;
> - ninguna pregunta puede necesitar conocimiento del mundo, ni que se le enseñen formas de decir;
> - usa nombres y cosas variados, y no repitas conjuntos anteriores.
>
> Guarda el archivo en la ruta indicada y no escribas nada más.

Después, otro subagente independiente valida las claves (que cada respuesta esperada se deduzca solo de lo dicho en la conversación) y corrige o elimina las dudosas; un tercero contesta las conversaciones exportadas sin ver lo esperado.
