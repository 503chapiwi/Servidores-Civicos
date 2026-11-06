# Procesador de reportes de servicio cívico (MAGA)

Aplicación de Streamlit que lee el formulario de Kobo *Servidor Cívico Informes* y llena la plantilla
"Reporte de horas de servicio cívico" (`plantilla.xlsx`) para un servidor y un mes.

## Archivos
- `app.py` – la interfaz de Streamlit (departamento y contraseña → servidor → mes → año → Descargar reporte)
- `kobo.py` – conexión con la API de Kobo, lectura de los envíos y exportación de la base de datos
- `reporte.py` – genera el reporte en Excel a partir de `plantilla.xlsx`
- `plantilla.xlsx` – la plantilla de septiembre; reemplázala para cambiar el diseño (mantén la misma estructura de filas)

## Publicar en Streamlit Community Cloud
1. Sube esta carpeta a un repositorio de GitHub (puede ser privado).
2. En share.streamlit.io: **Create app** → elige el repositorio, la rama `main` y el archivo principal `app.py`.
3. En **Advanced settings → Secrets**, pega el contenido de `.streamlit/secrets.toml.example`
   con las contraseñas reales y la llave de API de Kobo. Nunca subas contraseñas ni llaves reales a GitHub.
4. Publica la aplicación. Para cambiar los secretos después: App → Settings → Secrets.

## Acceso por departamento
La pantalla de inicio tiene una lista con los 22 departamentos y la opción "Nacional". Cada departamento
tiene su propia contraseña en la sección `[passwords]` de Secrets; el coordinador de un departamento solo
ve los servidores, reportes y datos de su departamento. Los departamentos sin contraseña no pueden entrar.
`ADMIN_PASSWORD` (o la anterior `APP_PASSWORD`) da acceso nacional.

Para habilitar un departamento, agrega una línea como `quiche = "..."` en `[passwords]` y guarda.
No hace falta cambiar el código ni volver a publicar. Los nombres van sin tildes, en minúsculas y con
`_` en lugar de espacios (por ejemplo `alta_verapaz`, `san_marcos`).

## Reglas que aplica el procesador
- Día trabajado: 8:00–16:00, 8 horas. Las actividades se escriben como `Participación, Tipo Tema`,
  una por línea; las comunidades, una por línea; las familias atendidas son la suma del día.
- Día no trabajado y asueto: "ASUETO", 0 horas. Día no trabajado sin asueto: "No laborado", 0 horas.
- Semana no enviada: aparecen las fechas con las filas en blanco. Semana enviada dos veces: se usa el envío más reciente.
- Los servidores se agrupan por CUI/NIT (se ignoran espacios, guiones y puntos); se muestra el nombre más reciente.
- Los datos se guardan en memoria por 10 minutos; el botón **Actualizar datos** los vuelve a descargar de Kobo.
