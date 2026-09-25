# Encargo fijo para redactar un conjunto de charla (G-54)

Se escribe antes de congelar `freeze-G-54` y no se cambia después. Se usa siempre el mismo texto, para que las cifras sean comparables en el tiempo. El redactor no recibe ningún otro contexto.

> Eres verificador independiente (regla 5.10), redactor de pruebas. No leas ningún repositorio ni código. Escribe un conjunto **nuevo** de charlas en español corriente, en un archivo UTF-8, con este formato:
> - una línea por turno: «lo que se dice», un TAB y «lo que se espera»;
> - una línea sin TAB se dice y no se califica;
> - una línea en blanco empieza una charla nueva;
> - una línea que empieza por «#» es un comentario.
>
> Lo esperado puede ser:
> - «sí», «no» o «no lo sé»: la respuesta debe empezar así;
> - «sin afirmar»: no debe afirmar ni negar;
> - una expresión regular entre barras, como `/lima/i`;
> - un texto corto que debe aparecer dentro de la respuesta.
>
> Contenido:
> - unas 32 preguntas calificadas, en 6 a 8 charlas;
> - en cada charla, una persona le cuenta a quien la escucha cosas de su vida y de la gente que la rodea, en primera persona, con frases de todos los días, como en una conversación real entre conocidos;
> - después, **la misma persona** le hace preguntas a quien la escuchó, para comprobar qué recuerda de lo que le contó;
> - mezcla preguntas de sí o no, preguntas abiertas (qué, quién, dónde, cuándo, cuántos) y algunas que deben contestarse «no lo sé» porque falta información;
> - ninguna pregunta puede necesitar conocimiento del mundo, ni que se le enseñen formas de decir;
> - usa nombres, lugares y temas variados, y no repitas conjuntos anteriores.
>
> Guarda el archivo en la ruta indicada y no escribas nada más.

Después, otro subagente independiente valida las claves con el mismo encargo de validación que la reserva: que cada respuesta esperada se deduzca solo de lo dicho en la charla. Corrige o elimina las claves dudosas. Un tercero contesta las charlas exportadas sin ver lo esperado.
