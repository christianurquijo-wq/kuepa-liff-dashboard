"""
Carga de datos y acciones de la sección EFE General.

- Lecturas de BigQuery: pasan por utils/bigquery.run_query (caché 10 min).
- KPIs históricos: pestaña EFE_KPI_HISTORICO del Sheet de operaciones ([ops] sheet_id),
  creada con scripts/efe_kpi_historico_setup.py.
- Acciones (antes eran botones del HTML de n8n, con un token de GitHub visible en la página):
    · Enviar reporte por correo -> POST al webhook n8n 'enviar-data-correo' (desde el servidor).
    · Generar reporte de riesgos -> repository_dispatch 'disparar_bot' al repo GitHub 'insights'
      con el token en secrets ([efe] github_token), nunca en el navegador.
"""
from __future__ import annotations

import gspread
import pandas as pd
import requests
import streamlit as st

from queries import efe as q
from utils import efe_metrics as m
from utils.bigquery import run_query as _run_query

PESTANA_HISTORICO = "EFE_KPI_HISTORICO"
WEBHOOK_CORREO = "https://n8n.kuepa.com/webhook/enviar-data-correo"


def run_query(sql: str) -> pd.DataFrame:
    """run_query con el error de BigQuery VISIBLE. Streamlit Cloud oculta el mensaje de las
    excepciones ("error message is redacted"); los errores de BigQuery no traen datos personales
    (tabla, columna, permiso), así que se muestran para poder diagnosticar."""
    try:
        return _run_query(sql)
    except Exception as exc:
        errores = getattr(exc, "errors", None) or []
        detalle = "; ".join(e.get("message", "") for e in errores if isinstance(e, dict)) or getattr(exc, "message", "") or str(exc)
        tabla = next((t for t in ("Seguimiento_DIARIO", "Empleabilidad_DIARIO", "Unificado_Seguimiento_APPEND",
                                  "Unificado_Empleabilidad_APPEND", "Unificado_Seguimiento", "Unificado_Satisfaccion",
                                  "Unificado_Caracterizacion", "Unificado_Empleabilidad") if t in sql), "BigQuery")
        st.error(f"Error de BigQuery al leer {tabla}: {detalle[:600]}")
        if "drive" in detalle.lower():
            st.info("La vista lee una hoja de Google Sheets vinculada: comparte esa hoja (Lector) con el correo "
                    "de la cuenta de servicio del dashboard.")
        st.stop()


def _cfg() -> dict:
    return dict(st.secrets.get("efe", {}))


# --------------------------------------------------------------------------- estado actual
def seguimiento(con_nombre: bool = False) -> pd.DataFrame:
    return m.prep_seguimiento(run_query(q.seguimiento(con_nombre)))


def satisfaccion() -> pd.DataFrame:
    return m.prep_satisfaccion(run_query(q.satisfaccion()))


def caracterizacion() -> pd.DataFrame:
    return m.prep_caracterizacion(run_query(q.caracterizacion()))


def empleabilidad() -> pd.DataFrame:
    return m.prep_empleabilidad(run_query(q.empleabilidad()))


# --------------------------------------------------------------------------- series
def _hay_diaria(tabla: str) -> bool:
    try:
        return int(_run_query(q.existe_tabla(tabla))["n"].iloc[0]) > 0  # sin mensaje: si falla, no hay diaria
    except Exception:
        return False


def serie_seguimiento() -> tuple[pd.DataFrame, bool]:
    """(serie, hay_foto_diaria)."""
    diaria = _hay_diaria("Seguimiento_DIARIO")
    sql = (q.serie_seguimiento if diaria else q.serie_seguimiento_solo_mensual)(m.IMPACTADO, m.RETENIDO, m.DESERCION)
    df = run_query(sql)
    if not df.empty:
        df["Fecha"] = pd.to_datetime(df["Fecha"])
        # Si un mes tiene foto diaria, manda la diaria (la mensual es la misma foto con menos detalle).
        if diaria:
            meses_diarios = set(df.loc[df["Origen"] == "diaria", "Fecha"].dt.to_period("M"))
            df = df[~((df["Origen"] == "mensual") & df["Fecha"].dt.to_period("M").isin(meses_diarios))]
    return df, diaria


def serie_empleabilidad() -> pd.DataFrame:
    df = run_query(q.serie_empleabilidad(m.CONTRATADO, con_diaria=_hay_diaria("Empleabilidad_DIARIO")))
    if not df.empty:
        df["Fecha"] = pd.to_datetime(df["Fecha"])
        diarios = set(df.loc[df["Origen"] == "diaria", "Fecha"].dt.to_period("M"))
        df = df[~((df["Origen"] == "mensual") & df["Fecha"].dt.to_period("M").isin(diarios))]
    return df


# --------------------------------------------------------------------------- KPIs históricos
@st.cache_resource
def _gs() -> gspread.Client:
    return gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]),
                                             scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])


@st.cache_data(ttl=600, show_spinner=False)
def kpi_historico() -> pd.DataFrame:
    ws = _gs().open_by_key(st.secrets["ops"]["sheet_id"]).worksheet(PESTANA_HISTORICO)
    valores = ws.get_all_values()
    if len(valores) <= 1:
        return pd.DataFrame(columns=valores[0] if valores else [])
    df = pd.DataFrame(valores[1:], columns=[c.strip().lower() for c in valores[0]])
    df = df[df["mes"].str.strip() != ""].copy()
    df["mes"] = df["mes"].str.strip().str[:7]
    for c in ("impactados", "nuevos", "retencion", "aprobacion", "nps", "satisfaccion"):
        if c in df:
            # admite coma decimal (si alguien escribe 82,5 en el Sheet)
            df[c] = pd.to_numeric(df[c].str.strip().str.replace("%", "").str.replace(",", "."), errors="coerce")
    df["grupo"] = df["grupo"].where(df["grupo"].str.strip() != "", df["proyecto"].map(m.GRUPOS)).fillna("Sin grupo")
    return df


# --------------------------------------------------------------------------- acciones
def enviar_correo(destinatarios: list[str], asunto: str, html: str, extra: dict) -> tuple[bool, str]:
    url = _cfg().get("webhook_correo", WEBHOOK_CORREO)
    try:
        r = requests.post(url, json={"destinatarios": destinatarios, "asunto": asunto, "html": html, **extra},
                          timeout=30)
    except requests.RequestException as exc:
        return False, f"Sin conexión con n8n: {exc}"
    if r.ok:
        return True, "Reporte enviado a " + ", ".join(destinatarios)
    return False, f"n8n respondió {r.status_code}: {r.text[:200]}"


def disparar_riesgos(correo: str) -> tuple[bool, str]:
    cfg = _cfg()
    token = cfg.get("github_token") or dict(st.secrets.get("ops", {})).get("github_token")
    if not token:
        return False, "Falta [efe] github_token en los secrets."
    repo = cfg.get("repo_riesgos", "christianurquijo-wq/insights")
    try:
        r = requests.post(
            f"https://api.github.com/repos/{repo}/dispatches",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"},
            json={"event_type": "disparar_bot", "client_payload": {"correo_usuario": correo}},
            timeout=20,
        )
    except requests.RequestException as exc:
        return False, f"Sin conexión con GitHub: {exc}"
    if r.status_code == 204:
        return True, f"Reporte de riesgos en proceso. Llegará a {correo}."
    if r.status_code == 404:
        return False, f"GitHub 404: el token no tiene acceso a {repo} (Contents: read & write)."
    return False, f"GitHub {r.status_code}: {r.text[:200]}"
