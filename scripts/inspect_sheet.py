"""
Utilidad de diagnóstico -- Google Sheets (equivalente a
scripts/inspect_schema.py, pero para hojas de cálculo en vez de tablas de
BigQuery).

No es parte de la app -- es una CLI para explorar una pestaña NUEVA antes
de escribir queries o páginas contra ella. Mismo criterio que
inspect_schema.py: no adivinar nombres de columna ni catálogos de valores
por una muestra chica.

Uso -- listar TODAS las pestañas de una hoja (nombre real, no posición):
    python scripts/inspect_sheet.py <spreadsheet_id>

Uso -- esquema + muestra de 5 filas de una pestaña puntual:
    python scripts/inspect_sheet.py <spreadsheet_id> "TiempoEnPool"

Uso -- distribución de valores de columnas específicas (para columnas de
"estado" donde hace falta ver TODOS los valores posibles, no adivinar):
    python scripts/inspect_sheet.py <spreadsheet_id> "TiempoEnPool" "Estado Patrocinio" "Estado del último proceso"

Uso -- lo mismo, pero filtrando filas primero (útil cuando la pestaña
mezcla varios programas/cohortes, como pasó con "TiempoEnPool" e
"Histórico" -- ambas traen Kuepa Colombia completo, no solo Ecolombia):
    python scripts/inspect_sheet.py <spreadsheet_id> "TiempoEnPool" "Estado Patrocinio" --filtro "Cohorte=ECOLOMBIA"

Un mismo --filtro admite varios valores separados por coma -- se
combinan con OR (útil para probar una hipótesis de "estos N estados
cuentan como el pool", sin tener que ir tanteando estado por estado):
    python scripts/inspect_sheet.py <spreadsheet_id> "TiempoEnPool" --filtro "Cohorte=ECOLOMBIA" --filtro "Estado Patrocinio=En Proceso,En ruta de empleabilidad,Carta de presentación,sin proceso,Proceso Avanzado,Caso especial"

`--filtro` se puede repetir (distintos --filtro se combinan con AND;
varios valores dentro del MISMO --filtro, separados por coma, se
combinan con OR) y puede ir en cualquier posición de los argumentos.

Uso -- conteo de valores DISTINTOS de una columna (ej. estudiantes
únicos por "Id CRM"), después de aplicar los filtros -- para validar
KPIs que Looker calcula como COUNT_DISTINCT y no como conteo de filas:
    python scripts/inspect_sheet.py <spreadsheet_id> "TiempoEnPool" --filtro "Cohorte=ECOLOMBIA" --distinct "Id CRM"

`--distinct` también se puede repetir y va en cualquier posición.

Uso -- lo mismo, pero DESGLOSADO por otra columna (ej. estudiantes
únicos por Programa, para el donut):
    python scripts/inspect_sheet.py <spreadsheet_id> "TiempoEnPool" --filtro "Cohorte=ECOLOMBIA" --distinct "Id CRM" --por "Programa"

Uso -- promedio de una columna NUMÉRICA (soporta decimales con coma,
"94,6"), opcionalmente desglosado con --por (ej. Tiempo en el Pool
promedio por cantidad de proceso, para el combo bar+line):
    python scripts/inspect_sheet.py <spreadsheet_id> "TiempoEnPool" --filtro "Cohorte=ECOLOMBIA" --promedio "Tiempo en el Pool" --por "cantidad de proceso"

Uso -- volcado de columnas TAL CUAL (sin distribución ni promedio) --
para bloques tipo "una fila por fecha" pegados al lado de la tabla
principal (ej. el histórico diario de KPIs dentro de "TiempoEnPool"),
donde value_counts() no sirve porque cada fecha es un valor distinto.
Descarta filas donde TODAS las columnas pedidas vienen vacías:
    python scripts/inspect_sheet.py <spreadsheet_id> "TiempoEnPool" "Fecha" "Postulaciones realizadas" "Promedio de dias en el pool" --tabla

Lee las credenciales de service_account.json (el mismo archivo que ya usa
inspect_schema.py), con scopes de Sheets/Drive de solo lectura -- el mismo
patrón de utils/sheets.py, pero sin depender de Streamlit (`st.secrets`)
para poder correr como script normal.

IMPORTANTE -- permisos: la hoja debe estar compartida como Viewer con el
client_email de ese service_account.json (búscalo abriendo el archivo, es
un campo de texto). Si no está compartida, esto falla con un error de
permisos de Google API (403), no con un error de Python -- es lo primero
a revisar si el script no corre.
"""
import sys
from pathlib import Path

import gspread
import pandas as pd

SERVICE_ACCOUNT_PATH = Path(__file__).resolve().parent.parent / "service_account.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _get_client() -> gspread.Client:
    return gspread.service_account(filename=str(SERVICE_ACCOUNT_PATH), scopes=SCOPES)


def _listar_pestanas(client: gspread.Client, spreadsheet_id: str) -> None:
    sh = client.open_by_key(spreadsheet_id)
    print(f"\n=== Pestañas de '{sh.title}' ===")
    for ws in sh.worksheets():
        print(f"  {ws.title!r:40s} {ws.row_count} filas x {ws.col_count} columnas (tamaño de grilla, no filas con dato)")


def _dedup_headers(headers: list) -> list:
    """get_all_records() de gspread revienta si el encabezado tiene
    columnas vacías o repetidas -- y ya nos pasó: varias pestañas de este
    proyecto tienen un bloque secundario pegado al lado del principal,
    con celdas de encabezado en blanco. Esta función nombra cada columna
    vacía/repetida de forma única para poder seguir leyendo la pestaña
    completa en vez de que truene."""
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


def _leer_pestana(client: gspread.Client, spreadsheet_id: str, worksheet_name: str) -> pd.DataFrame:
    """Usa get_all_values() en vez de get_all_records() -- este último
    exige encabezados únicos y no vacíos, y varias pestañas de esta hoja
    no cumplen eso (ver _dedup_headers)."""
    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(worksheet_name)
    valores = ws.get_all_values()
    if not valores:
        return pd.DataFrame()
    headers = _dedup_headers(valores[0])
    df = pd.DataFrame(valores[1:], columns=headers)
    # El tamaño de grilla de Sheets (row_count) casi siempre es mayor que
    # las filas con dato real -- se quitan las filas 100% vacías del final.
    df = df[~(df == "").all(axis=1)]
    return df.reset_index(drop=True)


def _mostrar_esquema(df: pd.DataFrame, worksheet_name: str) -> None:
    print(f"\n=== Esquema de '{worksheet_name}' ===")
    print(f"Filas con dato: {len(df):,}")
    for col in df.columns:
        print(f"  {col}")


def _mostrar_muestra(df: pd.DataFrame) -> None:
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    print("\n=== Muestra (5 filas) ===")
    print(df.head(5).to_string())


def _aplicar_filtros(df: pd.DataFrame, filtros: list) -> pd.DataFrame:
    """Cada filtro es 'Columna=Valor' (comparación exacta, como string --
    igual que lo que guarda Sheets). Varios --filtro se combinan con AND.
    Dentro de un mismo filtro, varios valores separados por coma se
    combinan con OR (ej. 'Estado Patrocinio=A,B,C') -- necesario para
    probar hipótesis de "estos N estados juntos son el pool" sin tener
    que filtrar estado por estado."""
    for filtro in filtros:
        if "=" not in filtro:
            print(f"Filtro inválido (falta '='): {filtro!r}")
            sys.exit(1)
        col, _, valores_raw = filtro.partition("=")
        col = col.strip()
        valores = [v.strip() for v in valores_raw.split(",")]
        if col not in df.columns:
            print(f"Filtro inválido: la columna {col!r} no existe en esta pestaña -- revisa el nombre exacto.")
            sys.exit(1)
        df = df[df[col].isin(valores)]
    return df


def _mostrar_distinct(df: pd.DataFrame, columnas: list, por: str = "") -> None:
    print("\n=== Conteo de valores distintos (COUNT_DISTINCT) ===")
    if por and por not in df.columns:
        print(f"\n-- --por {por!r}: NO EXISTE en esta pestaña -- revisa el nombre exacto arriba en 'Esquema' --")
        por = ""
    for col in columnas:
        if col not in df.columns:
            print(f"\n-- {col!r}: NO EXISTE en esta pestaña -- revisa el nombre exacto arriba en 'Esquema' --")
            continue
        distintos = df[col].nunique(dropna=False)
        print(f"  {col}: {distintos:,} valores distintos (sobre {len(df):,} filas)")
        if por:
            print(f"  -- desglosado por {por!r} --")
            for valor, sub in df.groupby(por, dropna=False):
                print(f"    {valor!r}: {sub[col].nunique(dropna=False):,} distintos ({len(sub):,} filas)")


def _a_numero(serie: pd.Series) -> pd.Series:
    """Convierte una columna de texto a número, tolerando decimales con
    coma (formato es-CO, tal cual lo guarda Sheets: '94,6') y celdas
    vacías (-> NaN, se ignoran en el promedio)."""
    return pd.to_numeric(
        serie.astype(str).str.strip().str.replace(",", ".", regex=False).replace({"": None}),
        errors="coerce",
    )


def _mostrar_promedio(df: pd.DataFrame, columnas: list, por: str = "") -> None:
    print("\n=== Promedio ===")
    if por and por not in df.columns:
        print(f"\n-- --por {por!r}: NO EXISTE en esta pestaña -- revisa el nombre exacto arriba en 'Esquema' --")
        por = ""
    for col in columnas:
        if col not in df.columns:
            print(f"\n-- {col!r}: NO EXISTE en esta pestaña -- revisa el nombre exacto arriba en 'Esquema' --")
            continue
        numeros = _a_numero(df[col])
        print(f"  {col}: promedio {numeros.mean():.2f} (sobre {numeros.notna().sum():,} filas con valor numérico, de {len(df):,} totales)")
        if por:
            print(f"  -- desglosado por {por!r} --")
            tmp = df[[por]].copy()
            tmp["_valor"] = numeros
            for valor, sub in tmp.groupby(por, dropna=False):
                sub_num = sub["_valor"]
                print(f"    {valor!r}: promedio {sub_num.mean():.2f} ({sub_num.notna().sum():,} filas, {len(sub):,} filas totales en este grupo)")


def _mostrar_tabla(df: pd.DataFrame, columnas: list) -> None:
    """Volcado tal cual de columnas puntuales -- para bloques 'una fila
    por fecha' pegados al lado de la tabla principal (value_counts() no
    sirve ahí porque cada fecha es distinta). Descarta filas donde TODAS
    las columnas pedidas vienen vacías."""
    print("\n=== Tabla ===")
    faltantes = [c for c in columnas if c not in df.columns]
    for c in faltantes:
        print(f"-- {c!r}: NO EXISTE en esta pestaña -- revisa el nombre exacto arriba en 'Esquema' --")
    columnas = [c for c in columnas if c in df.columns]
    if not columnas:
        return
    subset = df[columnas]
    subset = subset[~(subset == "").all(axis=1)]
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", 200)
    print(f"{len(subset):,} filas con al menos un valor en {columnas}")
    print(subset.to_string(index=False))


def _mostrar_crosstab(df: pd.DataFrame, filas: str, columnas: str) -> None:
    """Tabla cruzada (conteo) de dos columnas -- para encontrar qué
    combinación de una columna categórica (ej. Estado Patrocinio)
    reproduce un desglose ya conocido de otra (ej. Programa), o para
    series de tiempo tipo 'una fila por fecha x estado' (ej. el
    histórico), donde --tabla se queda corto porque hay que CONTAR, no
    solo volcar."""
    print("\n=== Crosstab ===")
    faltantes = [c for c in (filas, columnas) if c and c not in df.columns]
    for c in faltantes:
        print(f"-- {c!r}: NO EXISTE en esta pestaña -- revisa el nombre exacto arriba en 'Esquema' --")
    if faltantes:
        return
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", 250)
    ct = pd.crosstab(df[filas], df[columnas])
    ct["Total"] = ct.sum(axis=1)
    print(f"{filas!r} x {columnas!r} ({len(ct)} filas):")
    print(ct.to_string())


def _mostrar_distribucion(df: pd.DataFrame, columnas: list) -> None:
    print("\n=== Distribución de valores ===")
    for col in columnas:
        if col not in df.columns:
            print(f"\n-- {col!r}: NO EXISTE en esta pestaña -- revisa el nombre exacto arriba en 'Esquema' --")
            continue
        total = len(df)
        print(f"\n-- {col} ({df[col].nunique(dropna=False)} valores distintos, {total} filas) --")
        print(df[col].value_counts(dropna=False).to_string())


def main() -> None:
    # separa --filtro/--distinct/--promedio/--por/--tabla del resto de
    # argumentos posicionales, sin importar en qué orden los haya escrito
    filtros = []
    distinct_cols = []
    promedio_cols = []
    por = ""
    tabla = False
    crosstab_filas = ""
    crosstab_columnas = ""
    resto = []
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "--filtro":
            if i + 1 >= len(argv):
                print("Falta el valor de --filtro (ej: --filtro \"Cohorte=ECOLOMBIA\")")
                sys.exit(1)
            filtros.append(argv[i + 1])
            i += 2
        elif argv[i] == "--distinct":
            if i + 1 >= len(argv):
                print("Falta el valor de --distinct (ej: --distinct \"Id CRM\")")
                sys.exit(1)
            distinct_cols.append(argv[i + 1])
            i += 2
        elif argv[i] == "--promedio":
            if i + 1 >= len(argv):
                print("Falta el valor de --promedio (ej: --promedio \"Tiempo en el Pool\")")
                sys.exit(1)
            promedio_cols.append(argv[i + 1])
            i += 2
        elif argv[i] == "--por":
            if i + 1 >= len(argv):
                print("Falta el valor de --por (ej: --por \"Programa\")")
                sys.exit(1)
            por = argv[i + 1]
            i += 2
        elif argv[i] == "--tabla":
            tabla = True
            i += 1
        elif argv[i] == "--crosstab":
            if i + 2 >= len(argv):
                print("Faltan los 2 valores de --crosstab (ej: --crosstab \"DiaAppend\" \"Estado Patrocinio\")")
                sys.exit(1)
            crosstab_filas, crosstab_columnas = argv[i + 1], argv[i + 2]
            i += 3
        else:
            resto.append(argv[i])
            i += 1

    if not resto:
        print(
            "Uso: python scripts/inspect_sheet.py <spreadsheet_id> "
            "[pestaña] [columna1 columna2 ...] [--filtro \"Col=Valor[,Valor2,...]\"] "
            "[--distinct \"Columna\"] [--promedio \"Columna\"] [--por \"Columna\"] [--tabla] "
            "[--crosstab \"ColFilas\" \"ColColumnas\"]"
        )
        sys.exit(1)

    spreadsheet_id = resto[0]
    client = _get_client()

    if len(resto) == 1:
        _listar_pestanas(client, spreadsheet_id)
        return

    worksheet_name = resto[1]
    columnas = resto[2:]
    df = _leer_pestana(client, spreadsheet_id, worksheet_name)

    if filtros:
        antes = len(df)
        df = _aplicar_filtros(df, filtros)
        print(f"Filtro aplicado ({', '.join(filtros)}): {antes:,} -> {len(df):,} filas")

    _mostrar_esquema(df, worksheet_name)

    if tabla:
        _mostrar_tabla(df, columnas)
    elif columnas and not distinct_cols and not promedio_cols:
        _mostrar_distribucion(df, columnas)
    elif not columnas and not distinct_cols and not promedio_cols:
        _mostrar_muestra(df)

    if distinct_cols:
        _mostrar_distinct(df, distinct_cols, por=por)
    if promedio_cols:
        _mostrar_promedio(df, promedio_cols, por=por)
    if crosstab_filas or crosstab_columnas:
        _mostrar_crosstab(df, crosstab_filas, crosstab_columnas)


if __name__ == "__main__":
    main()
