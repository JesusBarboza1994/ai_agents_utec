# Imágenes del webchat

`salon.jpg` — foto de la sala, columna izquierda del chat de demostración.

La plantilla la carga como capa de fondo en `.vitrina`
(`app/web/templates/chat.html`). Si el archivo no está, el degradado de
respaldo sigue pintando y el panel se ve completo: no rompe la página.

Para cambiarla basta reemplazar el archivo con ese mismo nombre. Conviene una
imagen **vertical** (la columna es alta y angosta) y de menos de 500 KB, para
que la demostración cargue rápido.
