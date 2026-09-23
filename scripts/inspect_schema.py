"""
Utilidad de diagnóstico: imprime el esquema y una muestra de filas de
cualquier tabla (o VIEW) de BigQuery a la que el Service Account tenga
acceso.

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

Uso -- filtrando filas primero con --filtro "Columna=Valor[,Valor2,...]"
(varios --filtro se combinan con AND; varios valores separados por coma
dentro de un mismo --filtro se combinan con OR) -- mismo criterio que
scripts/inspect_sheet.py, para consistencia entre las dos herramientas:
    python scripts/inspect_schema.py sustained-edge-465417-m3.EFE_2026.Unificado_Satisfaccion --filtro "Proyecto=Ecolombia 2.0" NPS

Uso -- promedio de columnas numéricas, opcionalmente desglosado con
--por (ej. promedio de Evaluacion_docente por Proyecto):
    python scripts/inspect_schema.py sustained-edge-465417-m3.EFE_2026.Unificado_Satisfaccion --filtro "Proyecto=Ecolombia 2.0" --promedio "Evaluacion_docente" --promedio "Autoevaluacion" --por "Fecha_Append"

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


def _mostrar_esquema(client: bigquery.Client, tabla: str) -> bigquery.Table:
    """Devuelve el objeto Table -- lo necesitan _mostrar_muestra() y
    main() para saber si es una VIEW (list_rows() no funciona ahí, hay
    que consultarla con SQL en vez de tabledata.list -- nos pasó con
    Unificado_Satisfaccion)."""
    table = client.get_table(tabla)
    es_view = table.table_type == "VIEW"
    print(f"\n=== Esquema de {tabla} ({table.table_type}) ===")
    if es_view:
        # Una VIEW no reporta num_rows en los metadatos (siempre sale 0
        # o None) -- hay que contar con una query real.
        total = list(client.query(f"SELECT COUNT(*) AS n FROM `{tabla}`").result())[0]["n"]
        print(f"Filas totales: {total:,} (contadas con COUNT(*) -- es VIEW, no trae esto en metadatos)")
    else:
        print(f"Filas totales: {table.num_rows:,}")
    print(f"Última modificación: {table.modified}\n")
    for field in table.schema:
        modo = field.mode or ""
        print(f"  {field.name:40s} {field.field_type:12s} {modo}")
    return table


def _mostrar_muestra(client: bigquery.Client, tabla: str, table: bigquery.Table, where_sql: str) -> None:
    if table.table_type == "VIEW" or where_sql:
        # list_rows()/tabledata.list no soporta VIEWs (400 Bad Request:
        # "Cannot list a table of type VIEW") -- y tampoco acepta un
        # WHERE, así que con filtro también hay que usar SQL.
        query = f"SELECT * FROM `{tabla}` {where_sql} LIMIT 5"
        df = client.query(query).to_dataframe()
    else:
        rows = client.list_rows(table, max_results=5)
        df = rows.to_dataframe()
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    print("\n=== Muestra (5 filas) ===")
    print(df.to_string())


def _escapar(valor: str) -> str:
    return valor.replace("'", "\\'")


def _construir_where(filtros: list) -> str:
    """Cada filtro es 'Columna=Valor[,Valor2,...]' -- varios --filtro se
    combinan con AND, varios valores separados por coma DENTRO de un
    mismo --filtro se combinan con OR (IN (...)). Mismo criterio que
    scripts/inspect_sheet.py, para no tener dos sintaxis distintas en
    el mismo proyecto."""
    condiciones = []
    for filtro in filtros:
        if "=" not in filtro:
            print(f"Filtro inválido (falta '='): {filtro!r}")
            sys.exit(1)
        col, _, valores_raw = filtro.partition("=")
        col = col.strip()
        valores = [v.strip() for v in valores_raw.split(",")]
        lista_sql = ", ".join(f"'{_escapar(v)}'" for v in valores)
        condiciones.append(f"`{col}` IN ({lista_sql})")
    if not condiciones:
        return ""
    return "WHERE " + " AND ".join(condiciones)


def _mostrar_distribucion(client: bigquery.Client, tabla: str, columnas: list, where_sql: str) -> None:
    cols_sql = ", ".join(f"`{c}`" for c in columnas)
    query = f"SELECT {cols_sql} FROM `{tabla}` {where_sql}"
    df = client.query(query).to_dataframe()
    print("\n=== Distribución de valores ===")
    for col in columnas:
        total = len(df)
        print(f"\n-- {col} ({df[col].nunique(dropna=False)} valores distintos, {total} filas) --")
        print(df[col].value_counts(dropna=False).to_string())


def _mostrar_promedio(client: bigquery.Client, tabla: str, columnas: list, where_sql: str, por: str) -> None:
    columnas_sql = list(dict.fromkeys(columnas + ([por] if por else [])))
    cols_sql = ", ".join(f"`{c}`" for c in columnas_sql)
    query = f"SELECT {cols_sql} FROM `{tabla}` {where_sql}"
    df = client.query(query).to_dataframe()
    print("\n=== Promedio ===")
    for col in columnas:
        numeros = pd.to_numeric(df[col], errors="coerce")
        print(f"  {col}: promedio {numeros.mean():.2f} (sobre {numeros.notna().sum():,} filas con valor numérico, de {len(df):,} totales)")
        if por:
            tmp = df[[por]].copy()
            tmp["_valor"] = numeros
            print(f"  -- desglosado por {por!r} --")
            for valor, sub in tmp.groupby(por, dropna=False):
                sub_num = sub["_valor"]
                print(f"    {valor!r}: promedio {sub_num.mean():.2f} ({sub_num.notna().sum():,} filas, {len(sub):,} filas totales en este grupo)")


def main() -> None:
    filtros = []
    promedio_cols = []
    por = ""
    resto = []
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "--filtro":
            if i + 1 >= len(argv):
                print("Falta el valor de --filtro (ej: --filtro \"Proyecto=Ecolombia 2.0\")")
                sys.exit(1)
            filtros.append(argv[i + 1])
            i += 2
        elif argv[i] == "--promedio":
            if i + 1 >= len(argv):
                print("Falta el valor de --promedio (ej: --promedio \"Evaluacion_docente\")")
                sys.exit(1)
            promedio_cols.append(argv[i + 1])
            i += 2
        elif argv[i] == "--por":
            if i + 1 >= len(argv):
                print("Falta el valor de --por (ej: --por \"Fecha_Append\")")
                sys.exit(1)
            por = argv[i + 1]
            i += 2
        else:
            resto.append(argv[i])
            i += 1

    if not resto:
        print(
            "Uso: python scripts/inspect_schema.py <proyecto.dataset.tabla> "
            "[columna1 columna2 ...] [--filtro \"Col=Valor[,Valor2,...]\"] "
            "[--promedio \"Columna\"] [--por \"Columna\"]"
        )
        sys.exit(1)

    tabla = resto[0]
    columnas = resto[1:]
    where_sql = _construir_where(filtros)

    client = _get_client()
    table = _mostrar_esquema(client, tabla)
    if filtros:
        print(f"\nFiltro aplicado: {where_sql}")

    if promedio_cols:
        _mostrar_promedio(client, tabla, promedio_cols, where_sql, por)
    elif columnas:
        _mostrar_distribucion(client, tabla, columnas, where_sql)
    else:
        _mostrar_muestra(client, tabla, table, where_sql)


if __name__ == "__main__":
    main()
