# Procesador de reportes de servicio cívico (MAGA)

Streamlit app that reads the Kobo form *Servidor Cívico Timesheets* and fills the
"Reporte de horas de servicio cívico" template (`plantilla.xlsx`) for one servidor and month.

## Files
- `app.py` – the Streamlit interface (password → servidor → mes → año → Descargar reporte)
- `kobo.py` – Kobo API client, parsing of submissions, national database export
- `reporte.py` – builds the Excel report from `plantilla.xlsx`
- `plantilla.xlsx` – the September template; replace it to change the look (keep the same row layout)

## Deploy on Streamlit Community Cloud
1. Push this folder to a GitHub repo (the repo can be private).
2. On share.streamlit.io: **Create app** → pick the repo, branch `main`, main file `app.py`.
3. **Advanced settings → Secrets**: paste the contents of `.streamlit/secrets.toml.example`
   with your real password and Kobo API key. Never commit real secrets to GitHub.
4. Deploy. Changing secrets later: App → Settings → Secrets.

## Rules applied
- Worked day: 8:00–16:00, 8 hours. Activities written as `Tipo - Tema (Participación)`, one line each;
  communities one per line; families = sum for the day.
- Not worked + feriado: "Feriado", 0 hours. Not worked + not feriado: "No laborado", 0 hours.
- Week not submitted: dates shown, rows blank. Week submitted twice: latest submission wins.
- Servidores are grouped by CUI/NIT (spaces, dashes and dots ignored); the newest name is shown.
- Data are cached for 10 minutes; the **Actualizar datos** button reloads from Kobo.
