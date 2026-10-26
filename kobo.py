"""Lectura de los datos del formulario 'Servidor Cívico Timesheets' desde la API de KoboToolbox."""
import re
import unicodedata
from datetime import date, datetime, timedelta

import requests

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
SUFIJOS = ["", "_1", "_2", "_3", "_4"]          # lunes ... viernes en el formulario
CAMPOS_ACTIVIDAD = {"familias_atendidas", "comunidad", "actividad", "activity", "participacion"}


def norm(texto) -> str:
    """Minúsculas, sin tildes ni espacios sobrantes (para comparar textos)."""
    s = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def norm_cui(cui, nombre) -> str:
    c = re.sub(r"[\s\-\.]", "", str(cui or "")).upper()
    return c or "SIN-CUI:" + norm(nombre)


# ----------------------------------------------------------------------------- API

class KoboClient:
    def __init__(self, token: str, server: str = "https://kf.kobotoolbox.org"):
        self.server = server.rstrip("/")
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Token {token}"

    def _get(self, url, params=None):
        r = self.s.get(url, params=params, timeout=60)
        if r.status_code in (401, 403):
            raise PermissionError("Kobo rechazó la llave de API (revisa KOBO_TOKEN).")
        r.raise_for_status()
        return r.json()

    def find_asset_uid(self, enketo_id: str) -> str:
        """Busca el formulario cuyo enlace web (ee.kobotoolbox.org/x/<id>) coincide."""
        url, params = f"{self.server}/api/v2/assets/", {"format": "json", "limit": 200,
                                                         "q": "asset_type:survey"}
        candidatos = []
        while url:
            data = self._get(url, params)
            params = None
            for a in data.get("results", []):
                links = a.get("deployment__links")
                if links is None:
                    candidatos.append(a["uid"])
                elif any(enketo_id in str(v) for v in links.values()):
                    return a["uid"]
            url = data.get("next")
        for uid in candidatos:  # la lista no siempre trae los enlaces; revisar uno por uno
            links = self.get_asset(uid).get("deployment__links") or {}
            if any(enketo_id in str(v) for v in links.values()):
                return uid
        raise LookupError(f"No se encontró un formulario con el enlace …/x/{enketo_id} "
                          "en esta cuenta de Kobo.")

    def get_asset(self, uid: str) -> dict:
        return self._get(f"{self.server}/api/v2/assets/{uid}/", {"format": "json"})

    def get_submissions(self, uid: str) -> list:
        url, params, out = f"{self.server}/api/v2/assets/{uid}/data/", {"format": "json", "limit": 1000}, []
        while url:
            data = self._get(url, params)
            params = None
            out.extend(data.get("results", []))
            url = data.get("next")
        return out


# ----------------------------------------------------------------------- etiquetas

def label_maps(asset: dict):
    """Devuelve una función etiqueta(campo, valor) que traduce el nombre interno de una opción
    a su texto visible (p. ej. 'capacitacion' -> 'Capacitación')."""
    content = (asset or {}).get("content", {}) or {}
    listas = {}
    for c in content.get("choices", []):
        lab = c.get("label")
        if isinstance(lab, list):
            lab = next((x for x in lab if x), None)
        listas.setdefault(c.get("list_name"), {})[str(c.get("name"))] = lab or str(c.get("name"))
    campo_lista = {}
    for row in content.get("survey", []):
        nombre = row.get("name") or row.get("$autoname")
        lista = row.get("select_from_list_name")
        if not lista and str(row.get("type", "")).startswith("select_one "):
            lista = row["type"].split(" ", 1)[1].strip()
        if nombre and lista:
            campo_lista[re.sub(r"_\d+$", "", nombre)] = lista

    def etiqueta(campo, valor):
        if valor is None or valor == "":
            return ""
        lista = listas.get(campo_lista.get(campo), {})
        return lista.get(str(valor), str(valor))
    return etiqueta


# --------------------------------------------------------------------- parseo

def _hoja(clave: str) -> str:
    return clave.rsplit("/", 1)[-1]


def _buscar(sub: dict, nombre: str):
    for k, v in sub.items():
        if _hoja(k) == nombre:
            return v
    return None


def _si(v, etiqueta, campo):
    t = norm(etiqueta(campo, v))
    if t in ("si", "yes", "1", "true"):
        return True
    if t in ("no", "0", "false"):
        return False
    return None


def _mes(v, etiqueta):
    t = norm(etiqueta("mes", v))
    for i, m in enumerate(MESES):
        if t == norm(m):
            return i + 1
    d = re.sub(r"\D", "", str(v or ""))
    return int(d) if d and 1 <= int(d) <= 12 else None


def _entero(v):
    d = re.sub(r"[^\d]", "", str(v or "").split(".")[0])
    return int(d) if d else None


def _fecha_envio(sub):
    t = sub.get("_submission_time") or ""
    try:
        return datetime.fromisoformat(str(t).replace("Z", ""))
    except ValueError:
        return datetime.min


def parse_submission(sub: dict, etiqueta) -> dict | None:
    nombre = " ".join(str(_buscar(sub, "nombre") or "").split())
    anio, mes, semana = _entero(_buscar(sub, "ano")), _mes(_buscar(sub, "mes"), etiqueta), _entero(_buscar(sub, "semana"))
    if not (nombre and anio and mes and semana):
        return None
    dias = []
    for slot, sfx in enumerate(SUFIJOS):
        trabajo = _si(_buscar(sub, "trabajaste" + sfx), etiqueta, "trabajaste")
        feriado = _si(_buscar(sub, "feriado" + sfx), etiqueta, "feriado")
        acts = []
        for item in _buscar(sub, "actividades" + sfx) or []:
            campos = {re.sub(r"_\d+$", "", _hoja(k)): v for k, v in item.items()}
            campos = {k: v for k, v in campos.items() if k in CAMPOS_ACTIVIDAD}
            acts.append({
                "tipo": etiqueta("activity", campos.get("activity")),
                "tema": etiqueta("actividad", campos.get("actividad")),
                "participacion": etiqueta("participacion", campos.get("participacion")),
                "familias": _entero(campos.get("familias_atendidas")) or 0,
                "comunidad": str(campos.get("comunidad") or "").strip(),
            })
        dias.append({"slot": slot, "trabajo": trabajo, "feriado": feriado, "actividades": acts})
    return {
        "id": sub.get("_id"),
        "enviado": _fecha_envio(sub),
        "nombre": nombre,
        "cui": str(_buscar(sub, "cui") or "").strip(),
        "clave": norm_cui(_buscar(sub, "cui"), nombre),
        "departamento": etiqueta("departamento", _buscar(sub, "departamento")),
        "municipio": etiqueta("municipio", _buscar(sub, "municipio")),
        "anio": anio, "mes": mes, "semana": semana,
        "dias": dias,
    }


def parse_all(submissions: list, asset: dict) -> list:
    etiqueta = label_maps(asset)
    out = [parse_submission(s, etiqueta) for s in submissions]
    return [r for r in out if r]


# ---------------------------------------------------------------- calendario

def semanas_del_mes(anio: int, mes: int):
    """Semanas de lunes a viernes con al menos un día hábil en el mes (igual que el formulario).
    Devuelve [(numero_semana, [(slot, fecha), ...]), ...]."""
    primero = date(anio, mes, 1)
    wd = primero.weekday()
    desfase = 7 - wd if wd >= 5 else -wd
    semanas, n = [], 0
    while True:
        lunes = primero + timedelta(days=desfase + 7 * n)
        dias = [(d, lunes + timedelta(days=d)) for d in range(5) if (lunes + timedelta(days=d)).month == mes]
        if not dias:
            break
        semanas.append((n + 1, dias))
        n += 1
    return semanas


def ultimas_por_semana(registros: list, clave: str, anio: int, mes: int) -> dict:
    """Para un servidor y mes: el envío más reciente de cada semana."""
    elegidos = {}
    for r in registros:
        if r["clave"] == clave and r["anio"] == anio and r["mes"] == mes:
            prev = elegidos.get(r["semana"])
            if prev is None or (r["enviado"], r["id"] or 0) > (prev["enviado"], prev["id"] or 0):
                elegidos[r["semana"]] = r
    return elegidos


def resumen_dia(dia: dict | None) -> dict:
    """Convierte las respuestas de un día en lo que va en la fila del reporte."""
    if dia is None or dia["trabajo"] is None:
        return {"estado": None}
    if dia["trabajo"]:
        acts = dia["actividades"]
        lineas = [f"{a['tipo']} - {a['tema']} ({a['participacion']})" for a in acts if a["tipo"] or a["tema"]]
        comunidades = list(dict.fromkeys(a["comunidad"] for a in acts if a["comunidad"]))
        return {"estado": "trabajo", "actividades": "\n".join(lineas),
                "comunidades": "\n".join(comunidades),
                "familias": sum(a["familias"] for a in acts), "horas": 8}
    return {"estado": "feriado" if dia["feriado"] else "no_laborado",
            "actividades": "Feriado" if dia["feriado"] else "No laborado", "horas": 0}


def datos_reporte(registros: list, clave: str, anio: int, mes: int) -> dict:
    por_semana = ultimas_por_semana(registros, clave, anio, mes)
    semanas = []
    for num, dias in semanas_del_mes(anio, mes):
        envio = por_semana.get(num)
        filas = []
        for slot, fecha in dias:
            dia = envio["dias"][slot] if envio else None
            filas.append({"fecha": fecha, **resumen_dia(dia)})
        semanas.append({"numero": num, "dias": filas})
    todos = sorted(por_semana.values(), key=lambda r: r["enviado"])
    ultimo = todos[-1] if todos else next((r for r in sorted(registros, key=lambda r: r["enviado"], reverse=True)
                                           if r["clave"] == clave), None)
    return {
        "nombre": ultimo["nombre"] if ultimo else "",
        "departamento": ultimo["departamento"] if ultimo else "",
        "municipio": ultimo["municipio"] if ultimo else "",
        "anio": anio, "mes": mes, "semanas": semanas,
        "semanas_con_datos": sorted(por_semana),
    }


# ------------------------------------------------------------- base nacional

def tablas_nacionales(registros: list):
    """Una fila por día y una fila por actividad, usando solo el envío más reciente de cada
    semana por servidor. Sirve para analizar a nivel nacional."""
    import pandas as pd
    ultimos = {}
    for r in registros:
        k = (r["clave"], r["anio"], r["mes"], r["semana"])
        if k not in ultimos or (r["enviado"], r["id"] or 0) > (ultimos[k]["enviado"], ultimos[k]["id"] or 0):
            ultimos[k] = r
    fechas = {}
    dias, acts = [], []
    for r in ultimos.values():
        key = (r["anio"], r["mes"])
        if key not in fechas:
            fechas[key] = {n: dict(d) for n, d in semanas_del_mes(*key)}
        slots = fechas[key].get(r["semana"], {})
        base = {"CUI/NIT": r["cui"], "Nombre": r["nombre"], "Departamento": r["departamento"],
                "Municipio": r["municipio"], "Año": r["anio"], "Mes": MESES[r["mes"] - 1], "Semana": r["semana"]}
        for d in r["dias"]:
            if d["slot"] not in slots or d["trabajo"] is None:
                continue
            res = resumen_dia(d)
            estado = {"trabajo": "Trabajó", "feriado": "Feriado", "no_laborado": "No laborado"}[res["estado"]]
            fecha = slots[d["slot"]]
            dias.append({**base, "Fecha": fecha, "Estado": estado, "Horas": res["horas"],
                         "Actividades (#)": len(d["actividades"]) if d["trabajo"] else 0,
                         "Familias atendidas": res.get("familias", 0)})
            if d["trabajo"]:
                for a in d["actividades"]:
                    acts.append({**base, "Fecha": fecha, "Tipo": a["tipo"], "Tema": a["tema"],
                                 "Participación": a["participacion"], "Comunidad": a["comunidad"],
                                 "Familias atendidas": a["familias"]})
    orden = ["Departamento", "Municipio", "Nombre", "Fecha"]
    df_dias = pd.DataFrame(dias)
    df_acts = pd.DataFrame(acts)
    if not df_dias.empty:
        df_dias = df_dias.sort_values(orden)
    if not df_acts.empty:
        df_acts = df_acts.sort_values(orden)
    return df_dias, df_acts


def excel_nacional(registros: list) -> bytes:
    import io
    import pandas as pd
    dias, acts = tablas_nacionales(registros)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        acts.to_excel(xw, sheet_name="Actividades", index=False)
        dias.to_excel(xw, sheet_name="Días", index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns:
                ancho = max(len(str(c.value or "")) for c in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(ancho + 2, 10), 45)
        for nombre in ("Actividades", "Días"):
            ws = xw.book[nombre]
            for c in ws[1]:
                if c.value == "Fecha":
                    for cell in ws[c.column_letter][1:]:
                        cell.number_format = "dd/mm/yyyy"
    return buf.getvalue()
