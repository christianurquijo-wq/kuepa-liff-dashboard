
import gspread
import pandas as pd
import streamlit as st

SPREADSHEET_ID = "1objyGOm_rGMFnQCw7Xyx5rUHhOXWtm2gfUvH02saU34"

"""IDs de hojas de Sheets que tiene la automatización de actualización de datos de Hoja Vinculada con BQ"""
LECCIONES_ID = "1eHnGyIx2SruN1vxVyhYQ7v3pMcxl0v407aLxroSWl5Y"
USUARIOS_ID = "1ITzBWiF_S99sMHwQWUwoVOiqMJfd3NVumI4gcCmt3zQ"

EMPLEABILIDAD_SPREADSHEET_ID = "1i2cQ-sDyhgEi90YrQRCLiql5FMHbsPj5cvv7mQ6Sc1Y"

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


@st.cache_resource
def get_client() -> gspread.Client:
    return gspread.service_account_from_dict(
        dict(st.secrets["gcp_service_account"]),
        scopes=_SCOPES,
    )


@st.cache_data(ttl=600)
def read_sheet(worksheet_name: str, spreadsheet_id: str = SPREADSHEET_ID) -> pd.DataFrame:
    client = get_client()
    sheet = client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
    registros = sheet.get_all_records()
    return pd.DataFrame(registros)


def get_liff_data() -> pd.DataFrame:
    return read_sheet("LIF_Data_Export")


def _dedup_headers(headers: list) -> list:
    seen: dict = {}
    resultado = []
    for i, h in enumerate(headers):
        nombre = h.strip() if h.strip() else f"(col {i + 1})"
        if nombre in seen:
            seen[nombre] += 1
            nombre = f"{nombre} ({seen[nombre]})"
        else:
            seen[nombre] = 1
        resultado.append(nombre)
    return resultado


@st.cache_data(ttl=600)
def read_sheet_encabezados_sucios(worksheet_name: str, spreadsheet_id: str) -> pd.DataFrame:
    client = get_client()
    ws = client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
    valores = ws.get_all_values()
    if not valores:
        return pd.DataFrame()
    headers = _dedup_headers(valores[0])
    df = pd.DataFrame(valores[1:], columns=headers)
    df = df[~(df == "").all(axis=1)]
    return df.reset_index(drop=True)


def get_pool_empleabilidad() -> pd.DataFrame:
    return read_sheet_encabezados_sucios("TiempoEnPool", EMPLEABILIDAD_SPREADSHEET_ID)


def get_historico_empleabilidad() -> pd.DataFrame:
    return read_sheet_encabezados_sucios("Histórico", EMPLEABILIDAD_SPREADSHEET_ID)
