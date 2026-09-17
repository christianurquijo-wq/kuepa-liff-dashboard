"""
Utilidad de diagnóstico: imprime el esquema y una muestra de filas de
cualquier tabla de BigQuery a la que el Service Account tenga acceso.

No es parte de la app -- es una herramienta de línea de comandos para
explorar tablas NUEVAS antes de escribir queries/páginas contra ellas.
Úsala cada vez que empecemos un proyecto nuevo (Ecolombia, y los que
sigan), para no adivinar nombres de columnas ni formatos de datos.

Uso -- esquema + muestra de 5 filas (con el venv activado, desde la raíz
del proyecto):
    python scripts/inspect_schema.py sustained-edge-465417-m3.EFE_2026.ECOPLUS_V2_2026

Uso -- distribución de valores de columnas específicas (útil para
columnas de "estado" donde necesitas ver TODOS los valores posibles
antes de escribir la lógica de negocio, en vez de adivinar por una
muestra de 5 filas):
    python scripts/inspect_schema.py sustained-edge-465417-m3.EFE_2026.ECOPLUS_V2_2026 estado_academico estado__de_matricula etapa

Lee las credenciales directo de service_account.json (el mismo archivo
que ya usa la app) -- no depende de Streamlit ni de secrets.toml, así
que corre como script normal de Python, sin `streamlit run`.
"""
import sys
from pathlib import Path

import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

SERVICE_ACCOUNT_PATH = Path(__file__).resolve().parent.parent / "service_account.json"


def _get_client() -> bigquery.Client:
    credentials = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_PATH),
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return bigquery.Client(credentials=credentials, project=credentials.project_id)


def _mostrar_esquema(client: bigquery.Client, tabla: str) -> None:
    table = client.get_table(tabla)
    print(f"\n=== Esquema de {tabla} ===")
    print(f"Filas totales: {table.num_rows:,}")
    print(f"Última modificación: {table.modified}\n")
    for field in table.schema:
        modo = field.mode or ""
        print(f"  {field.name:40s} {field.field_type:12s} {modo}")


def _mostrar_muestra(client: bigquery.Client, tabla: str) -> None:
    table = client.get_table(tabla)
    rows = client.list_rows(table, max_results=5)
    df = rows.to_dataframe()
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    print("\n=== Muestra (5 filas) ===")
    print(df.to_string())


def _mostrar_distribucion(client: bigquery.Client, tabla: str, columnas: list) -> None:
    cols_sql = ", ".join(f"`{c}`" for c in columnas)
    query = f"SELECT {cols_sql} FROM `{tabla}`"
    df = client.query(query).to_dataframe()
    print("\n=== Distribución de valores ===")
    for col in columnas:
        total = len(df)
        print(f"\n-- {col} ({df[col].nunique(dropna=False)} valores distintos, {total} filas) --")
        print(df[col].value_counts(dropna=False).to_string())


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Uso: python scripts/inspect_schema.py <proyecto.dataset.tabla> "
            "[columna1 columna2 ...]"
        )
        sys.exit(1)

    tabla = sys.argv[1]
    columnas = sys.argv[2:]

    client = _get_client()
    _mostrar_esquema(client, tabla)

    if columnas:
        _mostrar_distribucion(client, tabla, columnas)
    else:
        _mostrar_muestra(client, tabla)


if __name__ == "__main__":
    main()
