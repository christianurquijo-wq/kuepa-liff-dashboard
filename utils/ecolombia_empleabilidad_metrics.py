"""
Ecolombia -- Pool de Empleabilidad.

Fuente: pestaña "TiempoEnPool" de la hoja "QUERY Postulaciones Kuepa
Colombia_V.1.0_03062026" (utils/sheets.py::get_pool_empleabilidad()).
Esa hoja trae Kuepa Colombia COMPLETO -- todas las cohortes y programas,
no solo Ecolombia+2026 -- así que enrich_pool() SIEMPRE filtra por
Cohorte == "ECOLOMBIA" antes de calcular nada. Confirmado con
scripts/inspect_sheet.py (365 filas quedan tras el filtro, sobre 999 en
total en la pestaña).

TODAS las reglas de este archivo están cruzadas número por número contra
el pantallazo de Looker "POOL DE EMPLEABILIDAD ECOLOMBIA+ 2026" -- no hay
ninguna pendiente. El método en cada caso fue: pedir el dump crudo de
las 365 filas (Id CRM, Programa, Estado Patrocinio, cantidad de proceso,
Tiempo en el Pool) vía inspect_sheet.py, y buscar POR CÓMPUTO (no a
ojo) qué combinación de columnas reproduce el número exacto del
pantallazo -- ver el detalle de cada regla abajo.

1) Contratados = 126
   Estado Patrocinio in {"Aprobado/Patrocinado", "Otro tipo de
   contrato"} -> 123 + 3 = 126.

2) Matrículas no exitosas = 76 / No patrocinable = 3
   Estado Patrocinio == "Matricula no Exitosa" -> 76 (match exacto).
   Estado Patrocinio == "No patrocinable" -> 3 (match exacto).

3) Activos = 263 / Sin proceso = 11 (4.2%)
   Activos = todo menos Matrícula no exitosa y Baja (365-76-26=263).
   Sin proceso = Estado Patrocinio == "sin proceso" -> 11/263 = 4.2%.

4) Estudiantes en pool = 112 (+ donut por Programa 58/34/20)
   NO es Contratados/No exitosa/Baja/No patrocinable, pero tampoco es
   simplemente "todo lo demás" -- se probaron las 2047 combinaciones no
   vacías de los 11 valores de Estado Patrocinio contra el desglose por
   Programa del pantallazo (Auxiliar de Mercadeo=58, Procesamiento y
   Digitación=34, Hotelería y Turismo=20) y SOLO UNA combinación
   reproduce los 3 números exactos:
       {"Carta de presentación", "Caso especial", "En Proceso",
        "Otro tipo de contrato", "Proceso Avanzado", "sin proceso"}
       -> 17+3+72+3+6+11 = 112 (58 Aux. Mercadeo + 34 Procesamiento +
          20 Hotelería, exacto).
   Nota contraintuitiva pero confirmada por el número, no por lógica de
   negocio: "En ruta de empleabilidad" (25 filas) NO cuenta como pool, y
   "Otro tipo de contrato" SÍ cuenta como pool aunque también cuente
   como Contratado -- Looker no trata estas categorías como una
   partición excluyente, así que un mismo estudiante puede aparecer en
   ambos KPIs. Sin duplicados de Id CRM dentro del pool (112 filas = 112
   Id CRM distintos, confirmado con --distinct).

5) Promedio de días en el pool = 94.6
   NO se calcula sobre los 112 del pool -- es el promedio de "Tiempo en
   el Pool" sobre TODAS las filas de Cohorte=ECOLOMBIA (260 de 365
   filas tienen valor; el resto viene en blanco) -> 94.6 exacto. Probado
   también restringido a "Activos" (263 filas): da el mismo 94.6, porque
   las filas en blanco de "Tiempo en el Pool" casi no se superponen con
   Matrícula no exitosa/Baja -- se usa la población más simple (todo
   Ecolombia) porque da el mismo resultado.

6) Postulaciones realizadas = 1.689
   SUM("cantidad de proceso") sobre TODAS las filas de Cohorte=ECOLOMBIA
   (346 de 365 filas tienen valor numérico) -> 1.689 exacto.

7) Combo "Cantidad de procesos por estudiante" x "Tiempo en el Pool"
   Mismo criterio que (5)/(6): se agrupa por "cantidad de proceso" sobre
   TODAS las filas de Cohorte=ECOLOMBIA (no solo el pool), contando
   estudiantes y promediando "Tiempo en el Pool" por cada valor de 0 a
   10.

8) Histórico (5 líneas: Contratados / En ruta de Empleabilidad / En
   proceso / Carta de presentación / Sin proceso, 13-ago a 18-sep-2026)
   Sale de la pestaña "Histórico" (get_historico_empleabilidad()), NO
   del bloque pre-calculado que vive al lado de la tabla principal en
   "TiempoEnPool" (ese está desactualizado desde el 13-ago-2026, 18
   filas nada más -- se descartó como fuente). "Histórico" trae Kuepa
   Colombia completo (18.871 filas) y una fila por estudiante POR CADA
   fecha de corte ("DiaAppend") -- filtrado a Cohorte=ECOLOMBIA quedan
   11.545 filas en 31 fechas (13-ago a 18-sep-2026, confirmado con
   --crosstab "DiaAppend" "Estado Patrocinio").

   Dato de calidad encontrado en ese crosstab: el 16-sep-2026 trae 730
   filas (exactamente el doble de un día normal, ~365) -- un
   duplicado de carga, no una fecha con más estudiantes. historico_pool()
   lo corrige de forma genérica (no hardcodeada a esa fecha): descarta
   duplicados por (Id CRM, DiaAppend) antes de agrupar, así que se
   autocorrige si vuelve a pasar en una carga futura.

   Las 5 series del gráfico se agregan así sobre esa base ya
   deduplicada:
     - Contratados = Aprobado/Patrocinado + Otro tipo de contrato
     - En ruta de Empleabilidad = En ruta de empleabilidad
     - En proceso = En Proceso
     - Carta de presentación = Carta de presentación
     - Sin proceso = sin proceso
   (Baja, Matricula no Exitosa, No patrocinable, Proceso Avanzado, Caso
   especial y Prospecto Caido NO aparecen en este gráfico -- no están en
   la leyenda del pantallazo.)
"""
import pandas as pd

ESTADOS_CONTRATADO = ["Aprobado/Patrocinado", "Otro tipo de contrato"]
ESTADO_NO_EXITOSA = "Matricula no Exitosa"
ESTADO_BAJA = "Baja"
ESTADO_NO_PATROCINABLE = "No patrocinable"
ESTADO_SIN_PROCESO = "sin proceso"

# Ver punto (4) del docstring del módulo -- única combinación de estados
# que reproduce 112 y el desglose exacto por Programa (58/34/20). NO es
# intuitivo (incluye "Otro tipo de contrato", excluye "En ruta de
# empleabilidad") -- no cambiar sin volver a validar contra Looker.
ESTADOS_POOL = [
    "Carta de presentación",
    "Caso especial",
    "En Proceso",
    "Otro tipo de contrato",
    "Proceso Avanzado",
    "sin proceso",
]

PROGRAMAS_CORTO = {
    "Técnico Laboral en Auxiliar de Mercadeo y Ventas": "Auxiliar de Mercadeo",
    "Técnico Laboral en Hotelería y Turismo": "Hotelería y Turismo",
    "Técnico Laboral en Procesamiento y Digitación de Bases de Datos": "Procesamiento y Digitación",
}


def enrich_pool(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Filtra "TiempoEnPool" a Cohorte == "ECOLOMBIA" -- la pestaña trae
    Kuepa Colombia completo, ver docstring del módulo."""
    if df_raw.empty or "Cohorte" not in df_raw.columns:
        return df_raw
    return df_raw[df_raw["Cohorte"] == "ECOLOMBIA"].reset_index(drop=True)


def _a_numero(serie: pd.Series) -> pd.Series:
    """Convierte una columna de texto a número, tolerando decimales con
    coma (formato es-CO, tal cual lo guarda Sheets: '94,6') y celdas
    vacías (-> NaN)."""
    return pd.to_numeric(
        serie.astype(str).str.strip().str.replace(",", ".", regex=False).replace({"": None}),
        errors="coerce",
    )


def resumen_estados(df: pd.DataFrame) -> dict:
    """KPIs confirmados -- ver puntos (1)-(3) del docstring del módulo.
    Todo a nivel de FILA sobre Cohorte=ECOLOMBIA."""
    total = len(df)
    if total == 0 or "Estado Patrocinio" not in df.columns:
        return {
            "total": 0, "contratados": 0, "no_exitosa": 0, "baja": 0,
            "no_patrocinable": 0, "sin_proceso": 0, "activos": 0, "pct_sin_proceso": 0.0,
        }

    estado = df["Estado Patrocinio"]
    contratados = int(estado.isin(ESTADOS_CONTRATADO).sum())
    no_exitosa = int((estado == ESTADO_NO_EXITOSA).sum())
    baja = int((estado == ESTADO_BAJA).sum())
    no_patrocinable = int((estado == ESTADO_NO_PATROCINABLE).sum())
    sin_proceso = int((estado == ESTADO_SIN_PROCESO).sum())
    activos = total - no_exitosa - baja
    pct_sin_proceso = (sin_proceso / activos * 100) if activos else 0.0

    return {
        "total": total, "contratados": contratados, "no_exitosa": no_exitosa,
        "baja": baja, "no_patrocinable": no_patrocinable, "sin_proceso": sin_proceso,
        "activos": activos, "pct_sin_proceso": pct_sin_proceso,
    }


def pool_empleabilidad(df: pd.DataFrame) -> pd.DataFrame:
    """Las filas que componen "Estudiantes en pool" (112) -- ver punto
    (4) del docstring del módulo. Sin duplicados de Id CRM (confirmado),
    así que len() de esto YA es el conteo distinto."""
    if df.empty or "Estado Patrocinio" not in df.columns:
        return df
    return df[df["Estado Patrocinio"].isin(ESTADOS_POOL)]


def programa_pool(df: pd.DataFrame) -> pd.DataFrame:
    """Desglose por Programa del pool (para el donut) -- ver punto (4).
    Nombres de Programa acortados para la gráfica (el original de Sheets
    es "Técnico Laboral en <nombre completo>")."""
    pool = pool_empleabilidad(df)
    if pool.empty or "Programa" not in pool.columns:
        return pd.DataFrame(columns=["Programa", "estudiantes"])
    programa_corto = pool["Programa"].map(PROGRAMAS_CORTO).fillna(pool["Programa"])
    conteo = programa_corto.value_counts().rename_axis("Programa").reset_index(name="estudiantes")
    return conteo


def promedio_dias_pool(df: pd.DataFrame) -> float:
    """Promedio de días en el pool = 94.6 -- ver punto (5) del docstring
    del módulo. OJO: NO se restringe a pool_empleabilidad(), se calcula
    sobre TODO Cohorte=ECOLOMBIA (confirmado que da el mismo resultado
    que restringir a "Activos", y es la definición más simple)."""
    if df.empty or "Tiempo en el Pool" not in df.columns:
        return 0.0
    return float(_a_numero(df["Tiempo en el Pool"]).mean())


def postulaciones_realizadas(df: pd.DataFrame) -> int:
    """Postulaciones realizadas = 1.689 -- ver punto (6) del docstring
    del módulo. SUM("cantidad de proceso") sobre TODO Cohorte=ECOLOMBIA."""
    if df.empty or "cantidad de proceso" not in df.columns:
        return 0
    return int(_a_numero(df["cantidad de proceso"]).sum())


def combo_procesos(df: pd.DataFrame) -> pd.DataFrame:
    """Datos para el combo "Cantidad de procesos por estudiante" (barra)
    x "Tiempo en el Pool" (línea) -- ver punto (7) del docstring del
    módulo. Sobre TODO Cohorte=ECOLOMBIA, agrupado por "cantidad de
    proceso" (0 a 10)."""
    columnas = ["cantidad de proceso", "estudiantes", "promedio_tiempo_pool"]
    if df.empty or "cantidad de proceso" not in df.columns or "Tiempo en el Pool" not in df.columns:
        return pd.DataFrame(columns=columnas)
    tmp = pd.DataFrame({
        "cantidad de proceso": _a_numero(df["cantidad de proceso"]),
        "Tiempo en el Pool": _a_numero(df["Tiempo en el Pool"]),
    }).dropna(subset=["cantidad de proceso"])
    agrupado = (
        tmp.groupby("cantidad de proceso")["Tiempo en el Pool"]
        .agg(estudiantes="size", promedio_tiempo_pool="mean")
        .reset_index()
        .sort_values("cantidad de proceso")
    )
    agrupado["cantidad de proceso"] = agrupado["cantidad de proceso"].astype(int)
    return agrupado.reset_index(drop=True)


# Ver punto (8) del docstring del módulo.
HISTORICO_SERIES = {
    "Contratados": ESTADOS_CONTRATADO,
    "En ruta de Empleabilidad": ["En ruta de empleabilidad"],
    "En proceso": ["En Proceso"],
    "Carta de presentación": ["Carta de presentación"],
    "Sin proceso": ["sin proceso"],
}


def historico_pool(df_historico_raw: pd.DataFrame) -> pd.DataFrame:
    """Serie diaria de las 5 categorías del histórico -- ver punto (8)
    del docstring del módulo. Recibe el DataFrame CRUDO de la pestaña
    "Histórico" (utils/sheets.py::get_historico_empleabilidad(), sin
    filtrar todavía) y devuelve un DataFrame ancho: una fila por fecha,
    una columna por cada una de las 5 categorías."""
    columnas_series = list(HISTORICO_SERIES.keys())
    columnas_vacias = ["Fecha"] + columnas_series
    requeridas = {"Cohorte", "DiaAppend", "Estado Patrocinio", "Id CRM"}
    if df_historico_raw.empty or not requeridas.issubset(df_historico_raw.columns):
        return pd.DataFrame(columns=columnas_vacias)

    df = df_historico_raw[df_historico_raw["Cohorte"] == "ECOLOMBIA"]
    if df.empty:
        return pd.DataFrame(columns=columnas_vacias)

    # Dato de calidad (ver punto 8): descartar duplicados de carga por
    # (Id CRM, DiaAppend) -- corrige de forma genérica el 16-sep-2026
    # (venía con el doble de filas) sin hardcodear esa fecha.
    df = df.drop_duplicates(subset=["Id CRM", "DiaAppend"])

    df = df.copy()
    df["_fecha"] = pd.to_datetime(df["DiaAppend"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["_fecha"])

    filas = []
    for fecha, sub in df.groupby("_fecha"):
        fila = {"Fecha": fecha}
        for serie, estados in HISTORICO_SERIES.items():
            fila[serie] = int(sub["Estado Patrocinio"].isin(estados).sum())
        filas.append(fila)

    resultado = pd.DataFrame(filas, columns=columnas_vacias).sort_values("Fecha").reset_index(drop=True)
    return resultado
