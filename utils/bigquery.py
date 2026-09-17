"""
Conexión a BigQuery -- un solo lugar para todo el proyecto.

Así evitamos el problema que teníamos en n8n: cada nodo Code repetía a mano
la misma lógica (y cuando había que corregir algo, como el bug de
`forzarSalida`, tocaba editar 6 nodos uno por uno). Aquí cualquier pestaña
nueva simplemente importa `run_query` de este archivo.
"""
from google.cloud import bigquery
from google.oauth2 import service_account
import pandas as pd
import streamlit as st


@st.cache_resource
def get_client() -> bigquery.Client:
    """
    Crea el cliente de BigQuery una sola vez por sesión de Streamlit.

    @st.cache_resource cachea el OBJETO (la conexión), no los datos.
    Sin esto, Streamlit re-ejecuta este archivo de arriba a abajo en cada
    interacción del usuario (cada filtro, cada click) -- y sin cache
    estaríamos reabriendo la conexión a BigQuery cientos de veces por
    sesión.
    """
    credentials_info = dict(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(
        credentials_info,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return bigquery.Client(credentials=credentials, project=credentials_info["project_id"])


@st.cache_data(ttl=600)  # 10 minutos -- ajusta según qué tan "en vivo" necesites la data
def run_query(sql: str) -> pd.DataFrame:
    """
    Ejecuta una query de BigQuery y devuelve un DataFrame de pandas.

    @st.cache_data cachea el RESULTADO de la query (no el cliente).
    Si el mismo SQL se pide de nuevo dentro de los 10 minutos, Streamlit
    devuelve la respuesta guardada en vez de volver a cobrarte/esperar
    la consulta en BigQuery.
    """
    client = get_client()
    return client.query(sql).to_dataframe()
