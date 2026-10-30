"""
Lectura/escritura del Google Sheet de operaciones (CATALOGO, LOG_EJECUCIONES,
SOLICITUDES).

Usa la MISMA cuenta de servicio del dashboard (st.secrets["gcp_service_account"])
pero con permiso de escritura, por eso tiene su propio cliente: el de
utils/sheets.py es de solo lectura y no se toca.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import gspread
import pandas as pd
import streamlit as st

from utils.ops_periodicidad import normalizar as normalizar_periodicidad

TZ = timezone(timedelta(hours=-5))
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _sheet_id() -> str:
    return st.secrets["ops"]["sheet_id"]


@st.cache_resource
def _cliente() -> gspread.Client:
    return gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]), scopes=_SCOPES)


def _hoja(nombre: str) -> gspread.Worksheet:
    return _cliente().open_by_key(_sheet_id()).worksheet(nombre)


def _si(valor) -> bool:
    return str(valor).strip().upper() in {"SI", "SÍ", "TRUE", "1", "YES"}


@st.cache_data(ttl=300, show_spinner=False)
def leer_catalogo() -> pd.DataFrame:
    df = pd.DataFrame(_hoja("CATALOGO").get_all_records())
    if df.empty:
        return df
    # get_all_records() convierte a número las celdas que lo parecen (ej. proyecto "512"):
    # todo se trata como texto salvo las columnas numéricas, o st.tabs y los filtros fallan.
    numericas = {"frecuencia_horas", "timeout_min"}
    for col in df.columns:
        if col not in numericas:
            df[col] = df[col].astype(str).str.strip()
    df = df[df["id"] != ""].copy()
    df["sensible"] = df["sensible"].map(_si)
    df["activo"] = df["activo"].map(_si)
    df["frecuencia_horas"] = pd.to_numeric(df["frecuencia_horas"], errors="coerce").fillna(0)
    df["timeout_min"] = pd.to_numeric(df["timeout_min"], errors="coerce").fillna(60)
    df["cwd"] = df["cwd"].replace("", "script")
    # Clave para cruzar con la bitácora (mismo formato que escribe ops_logger.py)
    df["automatizacion_id"] = df.apply(
        lambda r: f"n8n:{r['script']}" if r["plataforma"] == "n8n" else f"{r['repo']}:{r['script']}", axis=1
    )
    # oct-2026: periodicidad (etiqueta, filtro y desfase); alinea frecuencia_horas con el horario real
    return normalizar_periodicidad(df.reset_index(drop=True))


@st.cache_data(ttl=60, show_spinner=False)
def leer_log() -> pd.DataFrame:
    valores = _hoja("LOG_EJECUCIONES").get_all_values()
    if len(valores) <= 1:
        return pd.DataFrame(columns=valores[0] if valores else [])
    df = pd.DataFrame(valores[1:], columns=valores[0])
    df = df[df["id_ejecucion"] != ""].copy()
    for col in ("fecha_inicio", "fecha_fin"):
        df[col] = pd.to_datetime(df[col], errors="coerce", utc=True).dt.tz_convert(TZ)
    df["duracion_seg"] = pd.to_numeric(df["duracion_seg"], errors="coerce")
    # automatizacion_id viene como "owner/repo:script" desde GitHub o "repo:script"; normalizamos a "repo:script"
    df["automatizacion_id"] = df["automatizacion_id"].str.replace(r"^[^/:]+/", "", regex=True)
    return df.dropna(subset=["fecha_inicio"]).sort_values("fecha_inicio").reset_index(drop=True)


def registrar_solicitud(fila: dict) -> None:
    """Deja constancia de cada clic (aunque la ejecución nunca llegue a arrancar)."""
    columnas = ["request_id", "fecha", "usuario", "automatizacion_id", "nombre",
                "plataforma", "resultado", "detalle"]
    fila = {**fila, "fecha": datetime.now(TZ).isoformat(timespec="seconds")}
    try:
        _hoja("SOLICITUDES").append_row([str(fila.get(c, "")) for c in columnas], value_input_option="RAW")
    except Exception as exc:  # noqa: BLE001 -- no bloquear el disparo por el registro
        st.warning(f"No se pudo registrar la solicitud: {exc}")


@st.cache_data(ttl=10, show_spinner=False)
def leer_progreso() -> dict:
    """Hoja PROGRESO (la escriben los flujos de n8n que reportan su paso): {request_id: fila}.
    Si la hoja no existe o falla la lectura, devuelve {} y el panel usa el avance estimado."""
    try:
        filas = _hoja("PROGRESO").get_all_records()
    except Exception:  # noqa: BLE001 -- el progreso es opcional
        return {}
    return {str(f.get("request_id", "")).strip(): f for f in filas if str(f.get("request_id", "")).strip()}


def refrescar() -> None:
    leer_catalogo.clear()
    leer_log.clear()
