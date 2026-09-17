"""
Lectura de datos vía Google Sheets.

Usado por pestañas cuya consulta no puede correr directamente desde el
Service Account de BigQuery -- por ejemplo, LIFF Data, que depende de
DSGE_SIS (dataset del proyecto central que no tiene Service Accounts y que,
por política, no podemos duplicar dentro de BigQuery).

Arquitectura final (importante -- se descartaron dos intentos anteriores
antes de llegar a esta):

1. Se intentó un Connected Sheet de BigQuery ("Consulta_LIF") + una
   fórmula FILTER() en una pestaña espejo. No funcionó: una hoja conectada
   a BigQuery es de tipo DATA_SOURCE, y ni la API de Sheets (values.get,
   lo que usa este módulo) ni la mayoría de funciones de Sheets (FILTER
   incluida) pueden leer su rango directamente -- ambas fallan con
   variantes del mismo error ("400 Invalid range" / "FILTER no está
   disponible con datos vinculados").
2. Se intentó crear un extracto manual (Datos -> Extractos de datos) para
   obtener una copia en hoja normal. Tampoco resolvió el caso de uso aquí.
3. Solución final: un workflow de n8n (Schedule Trigger -> BigQuery
   Execute Query -> Google Sheets Clear + Append) consulta BigQuery
   DIRECTAMENTE -- con credenciales que sí tienen acceso a DSGE_SIS -- y
   escribe los resultados como valores planos en la pestaña
   "LIF_Data_Export". Ya no hay Connected Sheet ni extracto: n8n es la
   única fuente de verdad para esa pestaña, con un solo punto de refresco
   (el Schedule Trigger de n8n). La query que ejecuta ese nodo BigQuery es
   la misma que está documentada en queries/liff_data.py.

Este módulo de Python NUNCA ejecuta esa query -- solo lee, como una tabla
más, el resultado que n8n ya dejó escrito en "LIF_Data_Export".

Nota de permisos: la hoja de cálculo debe estar compartida como Viewer con
el client_email del mismo Service Account que usa utils/bigquery.py (está
en tu JSON de credenciales). Es un permiso de Drive, no de BigQuery -- no
toca el proyecto restringido para nada, y es independiente de las
credenciales que usa n8n para escribir ahí.
"""
import gspread
import pandas as pd
import streamlit as st

SPREADSHEET_ID = "1objyGOm_rGMFnQCw7Xyx5rUHhOXWtm2gfUvH02saU34"

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


@st.cache_resource
def get_client() -> gspread.Client:
    """
    Cliente de Sheets, cacheado por proceso (mismo patrón que
    utils/bigquery.py::get_client). Usa las mismas credenciales del
    Service Account, pero con scopes de Sheets/Drive de solo lectura --
    un scope distinto al de BigQuery, no un Service Account distinto.
    """
    return gspread.service_account_from_dict(
        dict(st.secrets["gcp_service_account"]),
        scopes=_SCOPES,
    )


@st.cache_data(ttl=600)
def read_sheet(worksheet_name: str, spreadsheet_id: str = SPREADSHEET_ID) -> pd.DataFrame:
    """
    Lee una hoja completa (encabezados en la fila 1) y la devuelve como
    DataFrame. Este cache es de 10 minutos, pero la frescura real del dato
    depende de cuándo corrió por última vez el Schedule Trigger de n8n --
    si necesitas datos más nuevos, primero verifica que el workflow de
    n8n ya corrió.
    """
    client = get_client()
    sheet = client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
    registros = sheet.get_all_records()
    return pd.DataFrame(registros)


def get_liff_data() -> pd.DataFrame:
    """
    Datos de la pestaña LIFF Data (extranjeros + nacionales juntos, ya
    distinguidos por la columna _POBLACION -- ver queries/liff_data.py
    para la query fuente).

    Lee de "LIF_Data_Export", que un workflow de n8n mantiene actualizada
    consultando BigQuery directamente (ver nota de arquitectura arriba).
    """
    return read_sheet("LIF_Data_Export")
