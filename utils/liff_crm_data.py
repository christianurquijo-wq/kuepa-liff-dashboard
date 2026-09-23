"""
Capa de datos -- LIFF Data / Matrícula + Académico (consulta unificada
CRM + SIS, sept-2026). Reemplaza a la query solo-SIS que usaba la página
LIFF Data original (ver queries/liff_data.py para el histórico de ambas).

Por qué esto es un módulo aparte de utils/sheets.py::get_liff_data():
- La query vieja vivía hardcodeada a UNA sola hoja (SPREADSHEET_ID fijo en
  utils/sheets.py). La nueva necesita poder apuntar a una hoja/pestaña
  distinta sin tocar código (mismo motivo que utils/iq_data.py -- ver su
  docstring), así que el sheet_id/worksheet viven en
  st.secrets["liff_crm"], con demo como fallback si no están configurados.
- También agrega el loader de la hoja de Satisfacción/Caracterización
  (st.secrets["satisfaccion"]). Esquema confirmado (sept-2026, pestaña
  "Satisfacción" del spreadsheet "LIF Data", gid=0): trae 4 columnas de
  puntaje agregado (TUTORES/CONTENIDO/PLATAFORMA/SERVICIO), una pregunta
  de NPS (0-10) y "Número de documento estudiante..." para cruzar. Pero
  la hoja todavía no tenía filas de respuestas reales al momento de
  diseñar esto (recién creada), así que el loader sigue sin validar tipos
  -- pages/1_LIFF_Data.py intenta parsear los puntajes como numéricos y
  cae a un perfil genérico por columna si no puede, en vez de asumir una
  escala que todavía no vimos poblada. La pestaña "Caracterización" (la
  otra tabla del mismo spreadsheet, con datos demográficos) queda
  PENDIENTE de conectar -- falta su gid/nombre de pestaña.

Arquitectura de carga (igual criterio que utils/iq_data.py):
  1. Service Account (gspread) -- utils.sheets.get_client().
  2. Fallback: exportación CSV pública (si la hoja es "cualquiera con el
     enlace").
  3. Demo -- si no hay st.secrets["liff_crm"] configurado, se lee
     data/liff/demo_matricula_academico.csv (datos SINTÉTICOS, mismo
     esquema exacto del SELECT final de la consulta unificada que trajo
     Christian) y la página avisa con un banner.

IMPORTANTE (paso pendiente de Christian, no de este código): la hoja de
cálculo debe estar compartida como Viewer con
stc3-editor@sustained-edge-465417-m3.iam.gserviceaccount.com (el mismo
Service Account que ya usa el resto del proyecto) -- sin eso, ni gspread
ni la exportación CSV van a poder leerla si no es pública.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

from utils.sheets import get_client

DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "liff"

# Columnas que trae el SELECT final de la consulta unificada CRM+SIS
# (queries/liff_data.py, sección "REPORTE FINAL UNIFICADO"). Si faltan acá,
# la página no puede calcular el funnel/calidad de datos -- se avisa con
# un error claro en vez de reventar más abajo con un KeyError.
CRM_REQUERIDAS = [
    "CREATED_AT_DATE", "CONTACT_DATA_FULL_NAME", "INCREMENTAL_LEAD_CODE",
    "LEAD_STATUS_DATA_NAME", "TIPO_MATRICULA", "CONTACT_DATA_ADNETWORK_NAME",
    "CAMPAIGN_DATA_NAME", "ENROLLMENT_DATA_AMOUNT_PAYED", "ENROLLMENT_DATA_AMOUNT_CONTRACT",
    "CONTACT_DATA_DOCUMENT_ID", "SALES_ADVISOR_FULL_NAME", "PROGRAMA_CRM",
    "INCREMENTAL_USER_CODE", "ALERTA_SIN_USUARIO_SIS",
]
# Columnas del bloque académico (Academico_Detalle) -- vienen en NULL para
# prematriculados y matriculados sin usuario SIS, eso es esperado, no un
# error de esquema.
ACADEMICO_COLUMNAS = [
    "_POBLACION", "DOCTYPE", "NOMBRE_SIS", "DOCUMENTO_SIS", "PROGRAMA_SIS", "CARRIL",
    "GRUPO", "FECHA_INICIO_GRUPO", "FECHA_FIN_GRUPO", "NOTA", "ESTADO_PUBLICACION",
    "ESTADO_APROBACION", "PROGRESO", "GROUP_ID", "PROGRAM_ID", "ESTADO_ACADEMICO",
]


def _url_export_csv(sheet_id: str, gid: str = "") -> str:
    base = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    return f"{base}&gid={gid}" if gid else base


def _config(seccion: str) -> dict:
    try:
        return dict(st.secrets.get(seccion, {}))
    except Exception:
        return {}


def _leer_via_gspread(sheet_id: str, worksheet: str = "", gid: str = "") -> pd.DataFrame:
    client = get_client()
    sh = client.open_by_key(sheet_id)
    if worksheet:
        ws = sh.worksheet(worksheet)
    elif gid:
        ws = sh.get_worksheet_by_id(int(gid))
    else:
        ws = sh.sheet1
    valores = ws.get_all_values()
    if not valores:
        return pd.DataFrame()
    df = pd.DataFrame(valores[1:], columns=valores[0])
    return df.replace("", pd.NA)


def _leer_via_csv_export(sheet_id: str, gid: str = "") -> pd.DataFrame:
    return pd.read_csv(_url_export_csv(sheet_id, gid), dtype=str, keep_default_na=True, na_values=[""])


@st.cache_data(ttl=3600, show_spinner="Cargando Matrícula + Académico (LIFF Data)...")
def load_liff_crm() -> tuple[pd.DataFrame, bool]:
    """Devuelve (df, es_demo). df sin tipar todavía -- ver
    utils/liff_metrics.py::enrich_crm() para las columnas derivadas."""
    cfg = _config("liff_crm")
    sheet_id = cfg.get("sheet_id")
    worksheet = cfg.get("worksheet", "")
    gid = cfg.get("gid", "")

    if not sheet_id:
        df = pd.read_csv(DEMO_DIR / "demo_matricula_academico.csv", dtype=str, keep_default_na=True, na_values=[""])
        return df, True

    try:
        df = _leer_via_gspread(sheet_id, worksheet, gid)
    except Exception:
        try:
            df = _leer_via_csv_export(sheet_id, gid)
        except Exception as e2:
            st.error(
                "No pude leer la hoja de Matrícula + Académico (ni por Service Account ni "
                "por exportación CSV). Verifica que esté compartida como Viewer con "
                "`stc3-editor@sustained-edge-465417-m3.iam.gserviceaccount.com`, y que "
                f"`sheet_id`/`worksheet` en secrets.toml sean correctos.\n\nDetalle: {e2}"
            )
            return pd.DataFrame(), False

    faltantes = [c for c in CRM_REQUERIDAS if c not in df.columns]
    if faltantes:
        st.error(
            f"La hoja de Matrícula + Académico no tiene las columnas necesarias: "
            f"{', '.join(faltantes)}. Revisa que la consulta se haya pegado completa."
        )
        return pd.DataFrame(), False

    return df, False


def liff_crm_limpiar_cache() -> None:
    load_liff_crm.clear()


# ---------------------------------------------------------------------------
# Satisfacción / Caracterización -- esquema TODAVÍA no confirmado (no se
# pudo leer la hoja para diseñar columnas). Este loader es deliberadamente
# genérico: no valida columnas ni aplica reglas de negocio, solo devuelve
# lo que venga. Una vez Christian comparta la hoja con el Service Account
# y confirmemos las columnas reales (en particular cuál es la de
# cédula/documento para cruzar), esto se reemplaza por un loader tipado
# igual que load_liff_crm() -- no antes, para no inventar reglas sobre
# datos que no hemos visto.
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner="Cargando Satisfacción / Caracterización...")
def load_satisfaccion() -> tuple[pd.DataFrame, str]:
    """Devuelve (df, estado). estado en {'ok', 'no_configurado', 'error'}."""
    cfg = _config("satisfaccion")
    sheet_id = cfg.get("sheet_id")
    worksheet = cfg.get("worksheet", "")
    gid = cfg.get("gid", "")

    if not sheet_id:
        return pd.DataFrame(), "no_configurado"

    try:
        df = _leer_via_gspread(sheet_id, worksheet, gid)
        return df, "ok"
    except Exception:
        try:
            df = _leer_via_csv_export(sheet_id, gid)
            return df, "ok"
        except Exception:
            return pd.DataFrame(), "error"


def satisfaccion_limpiar_cache() -> None:
    load_satisfaccion.clear()


_CANDIDATOS_CEDULA = ["cedula", "cédula", "documento", "document_id", "numero_documento", "num_documento", "identificacion", "identificación", "doc"]
_CANDIDATOS_NPS = ["recomendar", "recomendarías", "0 al 10", "escala del 0"]
_CANDIDATOS_GRUPO = ["grupo al que pertenece", "grupo"]
_CANDIDATOS_TUTOR = ["tutor del modulo", "selecciona el tutor"]


def _detectar_columna(df: pd.DataFrame, candidatos: list[str]) -> str | None:
    for col in df.columns:
        norm = str(col).strip().lower()
        if any(cand in norm for cand in candidatos):
            return col
    return None


def detectar_columna_documento(df: pd.DataFrame) -> str | None:
    """Heurística para encontrar la columna de cédula/documento en la hoja
    de satisfacción, para poder cruzarla contra CONTACT_DATA_DOCUMENT_ID
    del reporte CRM+SIS. Devuelve None si no encuentra nada parecido --
    en ese caso la página debe mostrar la hoja tal cual, sin cruzar."""
    return _detectar_columna(df, _CANDIDATOS_CEDULA)


def detectar_columna_nps(df: pd.DataFrame) -> str | None:
    """Pregunta "¿Qué tanto recomendarías...?" (escala 0-10) de la
    encuesta de Satisfacción real (sept-2026). El texto completo de la
    pregunta es largo y podría variar levemente, por eso es heurística y
    no un nombre exacto."""
    return _detectar_columna(df, _CANDIDATOS_NPS)


def detectar_columna_grupo(df: pd.DataFrame) -> str | None:
    return _detectar_columna(df, _CANDIDATOS_GRUPO)


def detectar_columna_tutor(df: pd.DataFrame) -> str | None:
    return _detectar_columna(df, _CANDIDATOS_TUTOR)


# Columnas de puntaje agregado confirmadas en la pestaña "Satisfacción"
# real (spreadsheet "LIF Data", gid=0) -- promedio de las preguntas tipo
# Likert de cada bloque. No sabemos todavía si vienen como número (ej.
# escala 1-5) o como texto, porque la hoja no tenía respuestas al
# momento de diseñar esto -- ver nota en pages/1_LIFF_Data.py.
SAT_COLUMNAS_SCORE = ["TUTORES", "CONTENIDO", "PLATAFORMA", "SERVICIO"]
