"""Procesador de reportes de horas de servicio cívico (MAGA).

Lee los envíos del formulario de Kobo y llena la plantilla 'Reporte de horas de servicio cívico'
para el servidor, mes y año elegidos.
"""
import hmac
from pathlib import Path

import streamlit as st

from kobo import (DEPARTAMENTOS, MESES, KoboClient, datos_reporte, excel_nacional, parse_all,
                  semanas_del_mes, slug)
from reporte import generar_reporte

PLANTILLA = Path(__file__).parent / "plantilla.xlsx"

st.set_page_config(page_title="Reportes de servicio cívico", page_icon="🌽", layout="centered")


def secreto(nombre, defecto=None):
    try:
        return st.secrets[nombre]
    except (KeyError, FileNotFoundError):
        return defecto


# ------------------------------------------------------------------ acceso por departamento
NACIONAL = "__nacional__"
MAX_INTENTOS = 5


def contrasena_de(depto: str):
    """Contraseña configurada en Secrets para un departamento (o la nacional)."""
    if depto == NACIONAL:
        return secreto("ADMIN_PASSWORD") or secreto("APP_PASSWORD")
    try:
        return st.secrets["passwords"][depto]
    except (KeyError, FileNotFoundError):
        return None


def pedir_acceso() -> bool:
    if st.session_state.get("depto"):
        return True
    st.title("Reportes de servicio cívico")
    opciones = [slug(d) for d in DEPARTAMENTOS] + [NACIONAL]
    nombres = {slug(d): d for d in DEPARTAMENTOS} | {NACIONAL: "Nacional (todos los departamentos)"}
    intentos = st.session_state.get("intentos", 0)
    if intentos >= MAX_INTENTOS:
        st.error("Demasiados intentos fallidos. Cierra esta pestaña y vuelve a abrir la página.")
        return False
    with st.form("login"):
        depto = st.selectbox("Departamento", opciones, format_func=nombres.get, index=None,
                             placeholder="Elige tu departamento")
        clave = st.text_input("Contraseña", type="password")
        entrar = st.form_submit_button("Entrar")
    if entrar:
        esperada = contrasena_de(depto) if depto else None
        if depto is None:
            st.error("Elige un departamento.")
        elif not esperada:
            st.error(f"{nombres[depto]} todavía no tiene acceso habilitado. "
                     "Pide la contraseña al coordinador nacional.")
        elif hmac.compare_digest(clave.encode(), str(esperada).encode()):
            st.session_state["depto"] = depto
            st.session_state["depto_nombre"] = nombres[depto]
            st.session_state.pop("intentos", None)
            st.rerun()
        else:
            st.session_state["intentos"] = intentos + 1
            st.error("Contraseña incorrecta.")
    return False


if not pedir_acceso():
    st.stop()

DEPTO = st.session_state["depto"]
with st.sidebar:
    st.write(f"**Acceso:** {st.session_state['depto_nombre']}")
    if st.button("Cerrar sesión"):
        for k in ("depto", "depto_nombre"):
            st.session_state.pop(k, None)
        st.rerun()


# ------------------------------------------------------------------ datos
@st.cache_data(ttl=600, show_spinner="Descargando datos de Kobo…")
def cargar_datos():
    cliente = KoboClient(secreto("KOBO_TOKEN"), secreto("KOBO_SERVER", "https://kf.kobotoolbox.org"))
    uid = secreto("KOBO_ASSET_UID") or cliente.find_asset_uid(secreto("KOBO_FORM", "GyRzS93l"))
    asset = cliente.get_asset(uid)
    return parse_all(cliente.get_submissions(uid), asset)


st.title("Reporte de horas de servicio cívico")

if not secreto("KOBO_TOKEN"):
    st.error("Falta la llave de API de Kobo (KOBO_TOKEN) en la configuración de la app.")
    st.stop()

col_a, col_b = st.columns([3, 1])
with col_b:
    if st.button("Actualizar datos", help="Vuelve a descargar los envíos de Kobo"):
        cargar_datos.clear()
try:
    registros = cargar_datos()
except Exception as e:  # mensaje claro en vez de un error técnico
    st.error(f"No se pudieron leer los datos de Kobo: {e}")
    st.stop()

# Cada coordinador solo ve los envíos de su departamento
if DEPTO != NACIONAL:
    registros = [r for r in registros if r["depto"] == DEPTO]

if not registros:
    st.info(f"Todavía no hay envíos de {st.session_state['depto_nombre']}.")
    st.stop()

# --- servidores, agrupados por CUI/NIT (se muestra el nombre del envío más reciente)
servidores = {}
for r in sorted(registros, key=lambda r: r["enviado"]):
    servidores[r["clave"]] = r
def etiqueta_servidor(clave):
    r = servidores[clave]
    return f"{r['nombre']}  (CUI/NIT {r['cui'] or 'sin dato'})"

with col_a:
    st.caption(f"{len(registros)} envíos · {len(servidores)} servidores")

clave = st.selectbox("Servidor cívico", sorted(servidores, key=lambda c: servidores[c]["nombre"].lower()),
                     format_func=etiqueta_servidor, index=None, placeholder="Elige un nombre")
if clave is None:
    st.stop()

propios = [r for r in registros if r["clave"] == clave]
meses = sorted({r["mes"] for r in propios})
reciente = max(propios, key=lambda r: r["enviado"])
c1, c2 = st.columns(2)
mes = c1.selectbox("Mes", meses, format_func=lambda m: MESES[m - 1],
                   index=meses.index(reciente["mes"]) if reciente["mes"] in meses else 0)
anios = sorted({r["anio"] for r in propios if r["mes"] == mes})
anio = c2.selectbox("Año", anios, index=len(anios) - 1)

datos = datos_reporte(registros, clave, anio, mes)
total_semanas = len(semanas_del_mes(anio, mes))
enviadas = datos["semanas_con_datos"]
faltan = [n for n in range(1, total_semanas + 1) if n not in enviadas]
if faltan:
    st.warning(f"Faltan las semanas {', '.join(map(str, faltan))} de {total_semanas}. "
               "Esas filas saldrán en blanco.")
else:
    st.success(f"Las {total_semanas} semanas del mes están enviadas.")

horas = sum(d.get("horas") or 0 for s in datos["semanas"] for d in s["dias"])
st.metric("Total de horas del mes", horas)

archivo = generar_reporte(str(PLANTILLA), datos)
nombre_archivo = f"Reporte_{datos['nombre'].replace(' ', '_')}_{MESES[mes - 1]}_{anio}.xlsx"
st.download_button("Descargar reporte", archivo, file_name=nombre_archivo, type="primary",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   use_container_width=True)
st.caption("El nombre del Encargado Departamental y las firmas se completan a mano.")

alcance = "nacional" if DEPTO == NACIONAL else st.session_state["depto_nombre"]
with st.expander(f"Base de datos ({alcance}): todas las actividades"):
    st.write("Un Excel con una fila por actividad y una fila por día de todos los servidores"
             + ("" if DEPTO == NACIONAL else f" de {alcance}")
             + ", para análisis. Si una semana se envió dos veces, se usa el envío más reciente.")
    st.download_button("Descargar base de datos", excel_nacional(registros),
                       file_name=f"Servicio_civico_base_{'nacional' if DEPTO == NACIONAL else DEPTO}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
