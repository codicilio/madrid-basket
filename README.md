# Madrid Basket — actualización automática

Dashboard pública para seguir la temporada 2026/27 del Real Madrid en Liga Endesa y Euroliga. La web se publica en GitHub Pages; un flujo automático vuelve a consultar los datos y republica el sitio aproximadamente cada cinco minutos. Dentro de la ventana prevista de un partido, la página consulta el archivo publicado cada minuto y muestra un botón para pedir la última versión disponible.

## Publicarla gratis en GitHub Pages

1. Descarga `madrid-basket-github.zip` y extráelo en tu ordenador. Los archivos de dentro del ZIP son la raíz del repositorio: deben quedar visibles `site`, `scripts`, `.github` y `README.md`.
2. En GitHub, crea un repositorio nuevo con un nombre sencillo, por ejemplo `madrid-basket`. Selecciona **Public**. Para GitHub Free, Pages requiere un repositorio público.
3. Instala y abre GitHub Desktop, inicia sesión y clona el repositorio vacío que acabas de crear.
4. Copia el contenido extraído del ZIP dentro de la carpeta local del repositorio. Copia también `.github`; contiene el flujo de publicación automática.
5. En GitHub Desktop, escribe un resumen como `Publicar dashboard Madrid Basket`, pulsa **Commit to main** y después **Push origin**.
6. En GitHub, abre el repositorio y entra en **Settings → Pages**. En **Build and deployment → Source**, selecciona **GitHub Actions**.
7. Abre la pestaña **Actions**, elige **Actualizar datos de baloncesto** y pulsa **Run workflow → Run workflow** para la primera publicación.
8. Espera a que la ejecución termine en verde. Después abre **Settings → Pages** y pulsa **Visit site**. La dirección tendrá este formato: `https://TU-USUARIO.github.io/NOMBRE-DEL-REPOSITORIO/`.
9. Envía esa dirección de Pages al grupo de WhatsApp. Comparte la dirección del sitio, no la del repositorio ni la del archivo local `index.html`.

La primera publicación puede tardar unos minutos. Si la pestaña **Actions** muestra un aviso para habilitar flujos de trabajo, habilítalos y vuelve a ejecutar el flujo.

## Qué hace y qué límites tiene

- El flujo obtiene el calendario, los resultados y las clasificaciones desde DBasket, y los horarios publicados desde las páginas de ACB y Real Madrid. Rechaza los datos incompletos para conservar la última versión válida.
- La tarea programada está configurada cada cinco minutos. GitHub puede retrasar una tarea programada cuando hay carga; no es una garantía de actualización exacta.
- La página solicita el último `data.json` al abrirse. Durante la ventana de un partido, vuelve a consultarlo cada minuto y muestra **Refrescar marcador**. Esto pide el último archivo publicado; no inicia un nuevo proceso en GitHub.
- En directo se muestra el marcador y el periodo cuando la fuente los publica. El botón de estadísticas abre la página en directo de ACB o Euroliga.
- Los escudos locales se guardan en `site/assets/logos/` y el flujo los copia al sitio publicado.
- Conserva la autorización escrita de DBasket junto al proyecto.
