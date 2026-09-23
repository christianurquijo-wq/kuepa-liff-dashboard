
from pathlib import Path

import pandas as pd
import streamlit as st

from utils.sheets import get_client

DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "iq"

USUARIOS_REQUERIDAS = [
    "PROGRAMA", "USER_ID", "ID_SIS", "TIME_VIEW",
    "MAX_LAST_ACCESS", "MAX_LAST_LOGIN", "MAX_LOG_DATE",
    "REGISTROS", "EFFECTIVE_LAST_ACCESS", "DAYS_SINCE_ACCESS",
]
USUARIOS_OPCIONALES = ["ACTIVE"]

LECCIONES_REQUERIDAS = [
    "Programa", "user_log_view", "Anio", "Fecha",
    "Horas_uso_raw", "Horas_uso_ajustada", "Nivel", "Tipo_nivel",
    "Area_Conocimiento", "Componente_academico", "ID_SIS", "Es_interno",
]
LECCIONES_OPCIONALES = ["id_log_view", "Status_pct"]

_COLUMNAS_TEXTO_CATEGORIA_USUARIOS = ["PROGRAMA"]
_COLUMNAS_TEXTO_CATEGORIA_LECCIONES = ["Programa", "Nivel", "Tipo_nivel", "Area_Conocimiento"]


def _url_export_csv(sheet_id: str, gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def _config_iq() -> dict:
    try:
        return dict(st.secrets.get("iq", {}))
    except Exception:
        return {}


def _leer_via_gspread(sheet_id: str, gid: str) -> pd.DataFrame:
    client = get_client()
    sh = client.open_by_key(sheet_id)
    ws = sh.get_worksheet_by_id(int(gid)) if gid not in (None, "") else sh.sheet1
    valores = ws.get_all_values()
    if not valores:
        return pd.DataFrame()
    df = pd.DataFrame(valores[1:], columns=valores[0])
    return df.replace("", pd.NA)


def _leer_via_csv_export(sheet_id: str, gid: str) -> pd.DataFrame:
    url = _url_export_csv(sheet_id, gid)
    return pd.read_csv(url, dtype=str, keep_default_na=True, na_values=[""])


def _cargar_hoja_o_demo(prefijo: str, archivo_demo: str) -> tuple[pd.DataFrame, bool]:
    cfg = _config_iq()
    sheet_id = cfg.get(f"{prefijo}_sheet_id")
    gid = cfg.get(f"{prefijo}_gid")

    if not sheet_id:
        return pd.read_csv(DEMO_DIR / archivo_demo, dtype=str, keep_default_na=True, na_values=[""]), True

    try:
        return _leer_via_gspread(sheet_id, gid), False
    except Exception:
        try:
            return _leer_via_csv_export(sheet_id, gid), False
        except Exception as e2:
            st.error(
                f"No pude leer la hoja '{prefijo}' de Google Sheets (ni por "
                f"Service Account ni por exportación CSV). Verifica que la "
                f"hoja esté compartida con el Service Account, o que el "
                f"sheet_id/gid en secrets.toml sean correctos.\n\nDetalle: {e2}"
            )
            return pd.DataFrame(), False


def _validar_esquema(df: pd.DataFrame, requeridas: list, nombre_hoja: str) -> bool:
    faltantes = [c for c in requeridas if c not in df.columns]
    if faltantes:
        st.error(
            f"La hoja '{nombre_hoja}' no tiene las columnas necesarias: "
            f"{', '.join(faltantes)}. Revisa 03_diccionario_datos.md o que "
            f"la consulta SQL se haya pegado completa en la pestaña."
        )
        return False
    return True


@st.cache_data(ttl=3600, show_spinner="Cargando usuarios de IQ...")
def load_iq_usuarios() -> tuple[pd.DataFrame, bool]:
    df, es_demo = _cargar_hoja_o_demo("usuarios", "demo_usuarios.csv")
    if df.empty:
        return df, es_demo
    if not _validar_esquema(df, USUARIOS_REQUERIDAS, "IQ_usuarios"):
        return pd.DataFrame(), es_demo

    columnas = USUARIOS_REQUERIDAS + [c for c in USUARIOS_OPCIONALES if c in df.columns]
    df = df[columnas].copy()

    for col in _COLUMNAS_TEXTO_CATEGORIA_USUARIOS:
        df[col] = df[col].astype("category")
    df["USER_ID"] = df["USER_ID"].astype(str)
    df["ID_SIS"] = df["ID_SIS"].astype(str).replace({"nan": pd.NA, "<NA>": pd.NA})
    df["TIME_VIEW"] = pd.to_numeric(df["TIME_VIEW"], errors="coerce").fillna(0).astype("int64")
    df["REGISTROS"] = pd.to_numeric(df["REGISTROS"], errors="coerce").fillna(0).astype("int64")
    df["DAYS_SINCE_ACCESS"] = pd.to_numeric(df["DAYS_SINCE_ACCESS"], errors="coerce")
    for col in ["MAX_LAST_ACCESS", "MAX_LAST_LOGIN", "MAX_LOG_DATE", "EFFECTIVE_LAST_ACCESS"]:
        df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    if "ACTIVE" in df.columns:
        df["ACTIVE"] = df["ACTIVE"].astype(str).str.strip().str.upper().isin(["TRUE", "1", "VERDADERO"])

    return df, es_demo


@st.cache_data(ttl=3600, show_spinner="Cargando lecciones de IQ...")
def load_iq_lecciones() -> tuple[pd.DataFrame, bool]:
    df, es_demo = _cargar_hoja_o_demo("lecciones", "demo_lecciones.csv")
    if df.empty:
        return df, es_demo
    if not _validar_esquema(df, LECCIONES_REQUERIDAS, "IQ_lecciones"):
        return pd.DataFrame(), es_demo

    columnas = LECCIONES_REQUERIDAS + [c for c in LECCIONES_OPCIONALES if c in df.columns]
    df = df[columnas].copy()

    for col in _COLUMNAS_TEXTO_CATEGORIA_LECCIONES:
        df[col] = df[col].astype("category")
    df["user_log_view"] = df["user_log_view"].astype(str)
    df["ID_SIS"] = df["ID_SIS"].astype(str).replace({"nan": pd.NA, "<NA>": pd.NA})
    df["Componente_academico"] = df["Componente_academico"].astype("category")
    df["Anio"] = pd.to_numeric(df["Anio"], errors="coerce").astype("Int64")
    df["Fecha"] = pd.to_datetime(df["Fecha"], utc=True, errors="coerce")
    df["Horas_uso_raw"] = pd.to_numeric(df["Horas_uso_raw"], errors="coerce")
    df["Horas_uso_ajustada"] = pd.to_numeric(df["Horas_uso_ajustada"], errors="coerce")
    if "Status_pct" in df.columns:
        df["Status_pct"] = pd.to_numeric(df["Status_pct"], errors="coerce")
    df["Es_interno"] = df["Es_interno"].astype(str).str.strip().str.upper().isin(["TRUE", "1", "VERDADERO"])
    return df, es_demo


def iq_limpiar_cache() -> None:
    load_iq_usuarios.clear()
    load_iq_lecciones.clear()
