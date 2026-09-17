"""
Reglas de negocio -- Ecolombia / Overview.

Fuente: BigQuery directo (`sustained-edge-465417-m3.EFE_2026.ECOPLUS_V2_2026`),
sin bridge de n8n/Sheets -- ver queries/ecolombia/overview.py para el SQL
exacto y utils/bigquery.run_query() para cómo se ejecuta.

Todo lo de abajo está confirmado número por número contra el pantallazo de
Looker (365 filas totales):

    Matriculados        novedad != "Matricula no exitosa"        289
    Activos              novedad == "Activo"                      263
    Deserciones          novedad == "Retiro"                       26
    % Deserción          Deserciones / Matriculados               9.00%
    % Retención          Activos / Matriculados                  91.00%
    No exitosas          novedad == "Matricula no exitosa"         76 (20.82% del total)
    Grupos               COUNT(DISTINCT grupo)                     21

`novedad_desercion` NO se usa -- es la misma columna duplicada que
`novedad` (siempre viene llena), y usarla con `.notna()` marcaba casi al
100% de los matriculados como desertores. Ese fue exactamente el bug que
se reportó ("ahora muestra 100% de deserción"); la causa raíz era esa
columna redundante, no la lógica de retención. Por la misma razón se quitó
`novedad_desercion` de queries/ecolombia/overview.py -- no aporta nada que
`novedad` no tenga ya.

`estado__de_matricula` y `estado_preinscripcion` tampoco se usan: tienen un
solo valor constante en las 365 filas, no discriminan nada.

Género/ciudad/grupos se agrupan sobre el universo de Matriculados (289) --
confirmado: género 96+193=289, ciudad 166+62+61=289.

Finalizados (forward-looking, confirmado con Christian):
    No existe un valor literal "Finalizado"/"Graduado" en las columnas de
    estado de la tabla -- se define como:
        cantidad_de_modulos_aprobados >= 8 AND fecha_de_finalizacionproductiva <= hoy
    Con la cohorte actual esto da 0 (nadie ha llegado a ese punto todavía)
    -- es el comportamiento esperado, no un bug.

Seleccionados / Pendientes por ingresar (tabla CONVOCATORIA, no V2_2026):
    Confirmado con Christian -- CONVOCATORIA es el embudo completo de
    candidatos (2704 filas: preinscripción, entrevista, matrícula), NO
    solo los ya matriculados. Por eso vive en funciones separadas
    (enrich_convocatoria / kpis_convocatoria) con su propia query
    (queries/ecolombia/convocatoria.py) -- es una fuente distinta a
    ECOPLUS_V2_2026, aunque comparten cohorte/programa/ciudad/grupo para
    poder filtrarse igual en la página.

        Seleccionados            resultado_entrevista in (Pasa, Repechaje)
        Pendientes por ingresar  Seleccionados AND estado_de_matricula != "Matriculado"

    Ambos son números vivos (la tabla se actualiza a diario con
    candidatos nuevos) -- no se validan contra un número congelado del
    pantallazo como Matriculados/Activos/Deserciones, sino por la
    definición de negocio.
"""
import pandas as pd

NOVEDAD_NO_EXITOSA = "Matricula no exitosa"
NOVEDAD_ACTIVO = "Activo"
NOVEDAD_RETIRO = "Retiro"
MODULOS_PARA_FINALIZAR = 8


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Formato explícito día/mes/año (confirmado en la muestra: "18/10/2027")
    # -- sin esto pandas adivina, y con fechas ambiguas (día <=12) puede
    # invertir día/mes en silencio. Mismo fix que ya se hizo en LIFF Data
    # para FECHA_INICIO_GRUPO.
    df["fecha_de_finalizacionproductiva"] = pd.to_datetime(
        df["fecha_de_finalizacionproductiva"], format="%d/%m/%Y", errors="coerce"
    )
    hoy = pd.Timestamp.now().normalize()

    df["_MATRICULADO"] = df["novedad"] != NOVEDAD_NO_EXITOSA
    df["_ACTIVO"] = df["novedad"] == NOVEDAD_ACTIVO
    df["_DESERTO"] = df["novedad"] == NOVEDAD_RETIRO
    df["_FINALIZADO"] = (
        df["_ACTIVO"]
        & (df["cantidad_de_modulos_aprobados"] >= MODULOS_PARA_FINALIZAR)
        & df["fecha_de_finalizacionproductiva"].notna()
        & (df["fecha_de_finalizacionproductiva"] <= hoy)
    )
    return df


def kpis_overview(df: pd.DataFrame) -> dict:
    total = len(df)
    matriculados = int(df["_MATRICULADO"].sum())
    no_exitosas = total - matriculados
    deserciones = int(df["_DESERTO"].sum())
    activos = int(df["_ACTIVO"].sum())
    finalizados = int(df["_FINALIZADO"].sum())
    grupos_activos = int(df["grupo"].nunique())

    pct_desercion = (deserciones / matriculados * 100) if matriculados else 0.0
    pct_retencion = (activos / matriculados * 100) if matriculados else 0.0
    pct_no_exitosa = (no_exitosas / total * 100) if total else 0.0

    return {
        "matriculados": matriculados,
        "activos": activos,
        "deserciones": deserciones,
        "pct_desercion": pct_desercion,
        "pct_retencion": pct_retencion,
        "no_exitosas": no_exitosas,
        "pct_no_exitosa": pct_no_exitosa,
        "grupos_activos": grupos_activos,
        "finalizados": finalizados,
    }


def grupos_por_programa(df: pd.DataFrame) -> pd.DataFrame:
    """Matriculados por programa -- insumo de la barra apilada."""
    d = df[df["_MATRICULADO"]]
    out = d.groupby("programa").size().reset_index(name="estudiantes")
    return out.sort_values("estudiantes", ascending=False)


def tabla_grupos(df: pd.DataFrame) -> pd.DataFrame:
    """Un renglón por grupo -- programa, ciudad, fechas y tamaño.
    Insumo tanto de la tabla de grupos como del gantt."""
    d = df[df["_MATRICULADO"]]
    out = (
        d.groupby("grupo")
        .agg(
            programa=("programa", "first"),
            ciudad=("ciudad", "first"),
            inicio=("fecha_inicio_group_id", "min"),
            fin=("fecha_fin_group_id", "max"),
            estudiantes=("grupo", "size"),
            activos=("_ACTIVO", "sum"),
        )
        .reset_index()
    )
    out["inicio"] = pd.to_datetime(out["inicio"], errors="coerce")
    out["fin"] = pd.to_datetime(out["fin"], errors="coerce")
    return out.sort_values("inicio")


def genero_counts(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["_MATRICULADO"]]
    return d.groupby("sexo").size().reset_index(name="cantidad")


def ciudad_counts(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["_MATRICULADO"]]
    out = d.groupby("ciudad").size().reset_index(name="estudiantes")
    return out.sort_values("estudiantes", ascending=False)


# ---------------------------------------------------------------------------
# CONVOCATORIA -- embudo de candidatos (Seleccionados / Pendientes por
# ingresar). Fuente distinta a todo lo de arriba -- ver docstring del
# módulo para la definición confirmada con Christian.
# ---------------------------------------------------------------------------
RESULTADO_SELECCIONADO = ("Pasa", "Repechaje")
ESTADO_MATRICULA_OK = "Matriculado"


def enrich_convocatoria(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["_SELECCIONADO"] = df["resultado_entrevista"].isin(RESULTADO_SELECCIONADO)
    df["_MATRICULADO_CONV"] = df["estado_de_matricula"] == ESTADO_MATRICULA_OK
    return df


def kpis_convocatoria(df: pd.DataFrame) -> dict:
    seleccionados = int(df["_SELECCIONADO"].sum())
    pendientes_por_ingresar = int(
        (df["_SELECCIONADO"] & ~df["_MATRICULADO_CONV"]).sum()
    )
    return {
        "seleccionados": seleccionados,
        "pendientes_por_ingresar": pendientes_por_ingresar,
    }
