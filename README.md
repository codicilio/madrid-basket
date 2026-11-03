# Madrid Basket

Dashboard de aficionados del Real Madrid de baloncesto (Liga Endesa y Euroliga), publicada gratis en GitHub Pages:

**https://codicilio.github.io/madrid-basket/**

## Qué incluye

- **Directo**: marcador, cuarto y reloj del partido en curso, actualizados cada 15 segundos desde las fuentes oficiales de Euroliga y ACB.
- **Estadísticas en vivo (Euroliga)**: tabla de jugadores del Madrid y del rival (puntos, rebotes, asistencias, tiros, valoración, quién está en pista) y parciales por cuarto. En ACB, enlace directo a las estadísticas oficiales del partido.
- **Próximo partido**: cuenta atrás, hora de Madrid, canales de TV (ACB) y botón para añadirlo al calendario del móvil.
- **Resumen de temporada**: balance, racha, últimos cinco partidos, puntos a favor y en contra y posición en cada competición.
- **Calendario y resultados** con filtros por competición, casa/fuera y rival. Al pulsar un partido de Euroliga ya jugado se abre su ficha completa con estadísticas.
- **Clasificaciones** de Liga Endesa y Euroliga con las zonas de playoff y play-in.
- **Compartir por WhatsApp** con el próximo partido ya escrito en el mensaje.

## Cómo se actualiza

- `.github/workflows/update.yml` se ejecuta cada 5 minutos (GitHub puede retrasarlo algunos minutos) y cada vez que se cambia el código.
- `scripts/update_data.py` descarga resultados y clasificaciones de DBasket (uso autorizado por escrito) y completa horarios exactos, televisión y marcador desde las APIs públicas de ACB y Euroliga. Si una fuente oficial falla, se mantienen los datos de DBasket. Si DBasket falla, no se publica nada y la web sigue mostrando la última versión válida.
- Solo se vuelve a publicar la web cuando cambia algún dato deportivo.
- Durante el partido, la propia página consulta directamente el marcador oficial, sin esperar a GitHub.

## Estructura

```
site/index.html        la web (un solo archivo, sin dependencias)
site/data.json         datos (los regenera el flujo automático)
site/assets/logos/     escudos
scripts/update_data.py recogida de datos
.github/workflows/     publicación automática
```

## Si algo falla

Pestaña **Actions → Actualizar datos de baloncesto → Run workflow** fuerza una actualización y publicación. Si sale en rojo, abre la ejecución para ver el error.
