# Monitor del Congreso

Votaciones de sala de la Cámara de Diputados y el Senado de Chile desde el 11-03-2026, para el recurso "Monitor del Congreso" de agenda-publica.com.

- `actualizar.py` baja los datos (opendata.camara.cl, web-back.senado.cl, tramitacion.senado.cl) y escribe `datos/congreso.json` y `datos/proyectos.json`. `cache/` guarda lo ya descargado para que la corrida diaria solo pida lo nuevo.
- `.github/workflows/actualizar.yml` lo corre todos los días a las 6:00 de Chile y sube los datos. Se puede lanzar a mano desde la pestaña Actions (Run workflow).
- La página (`página web/sitio/recursos/congreso/`) lee los datos desde `raw.githubusercontent.com/brojasgonzalo/monitor-congreso/main/datos/` y, si no responde, desde su copia local.
