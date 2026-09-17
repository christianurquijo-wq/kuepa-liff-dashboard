"""
Ecolombia -- Overview general.

Fuente: BigQuery directo (sin bridge de n8n/Sheets, a diferencia de LIFF
Data) -- ver queries/ecolombia/overview.py y utils/bigquery.run_query().

Las reglas de negocio (qué es "matriculado", "activo", "desertó",
"finalizado", "seleccionado") NO viven aquí -- están en
utils/ecolombia_metrics.py, con la justificación de cada una. Si un número
no cuadra contra el Looker, revisa ese archivo primero.

"Seleccionados" y "Pendientes por ingresar" vienen de una tabla distinta
(CONVOCATORIA, el embudo completo de candidatos) a la del resto de la
página (ECOPLUS_V2_2026, solo matriculados) -- por eso se consultan y
enriquecen por separado más abajo.

Clic-para-filtrar: las 3 gráficas de categoría simple (Programa, Género,
Ciudad) tienen on_select -- un clic en una barra/porción actualiza el
selectbox correspondiente, igual que si lo eligieras del dropdown. Ver
utils/ui.click_to_filter() para el mecanismo. El gantt y la tabla de
grupos NO son clickeables a propósito (no tienen un mapeo directo a un
filtro de una sola columna).
"""
import plotly.express as px
import streamlit as st

from queries.ecolombia.convocatoria import get_convocatoria_query
from queries.ecolombia.overview import get_overview_query
from utils.bigquery import run_query
from utils.ecolombia_metrics import (
    ciudad_counts,
    enrich,
    enrich_convocatoria,
    genero_counts,
    grupos_por_programa,
    kpis_convocatoria,
    kpis_overview,
    tabla_grupos,
)
from utils.ui import (
    AMARILLO,
    AZUL,
    CHART_HEIGHT,
    GRIS,
    NARANJA,
    ROJO,
    VERDE,
    badge,
    click_to_filter,
    dark,
    inject_css,
    kpi_row,
)

inject_css()

with st.spinner("Consultando BigQuery..."):
    df_raw = run_query(get_overview_query())
    df_conv_raw = run_query(get_convocatoria_query())

if df_raw.empty:
    st.warning("ECOPLUS_V2_2026 no devolvió filas. Revisa el acceso del Service Account.")
    st.stop()

df_full = enrich(df_raw)
df_conv_full = enrich_convocatoria(df_conv_raw)

# ---------------------------------------------------------------------------
# Encabezado + filtros
# ---------------------------------------------------------------------------
col_title, col_badge = st.columns([5, 1], vertical_alignment="center")
col_title.title("Ecolombia -- Overview")
col_badge.markdown(badge(f"{len(df_full)} REGISTROS"), unsafe_allow_html=True)
st.caption("ECOPLUS_V2_2026 -- todas las cohortes, todos los programas")

with st.container(border=True):
    f1, f2, f3, f4, f5 = st.columns(5)
    cohortes = ["Todas"] + sorted(df_full["cohorte"].dropna().unique().tolist())
    programas = ["Todos"] + sorted(df_full["programa"].dropna().unique().tolist())
    ciudades = ["Todas"] + sorted(df_full["ciudad"].dropna().unique().tolist())
    grupos = ["Todos"] + sorted(df_full["grupo"].dropna().unique().tolist())
    generos = ["Todos"] + sorted(df_full["sexo"].dropna().unique().tolist())

    cohorte_sel = f1.selectbox("Cohorte", cohortes, key="eco_cohorte_sel")
    programa_sel = f2.selectbox("Programa", programas, key="eco_programa_sel")
    ciudad_sel = f3.selectbox("Ciudad", ciudades, key="eco_ciudad_sel")
    grupo_sel = f4.selectbox("Grupo", grupos, key="eco_grupo_sel")
    sexo_sel = f5.selectbox("Género", generos, key="eco_sexo_sel")

df = df_full.copy()
if cohorte_sel != "Todas":
    df = df[df["cohorte"] == cohorte_sel]
if programa_sel != "Todos":
    df = df[df["programa"] == programa_sel]
if ciudad_sel != "Todas":
    df = df[df["ciudad"] == ciudad_sel]
if grupo_sel != "Todos":
    df = df[df["grupo"] == grupo_sel]
if sexo_sel != "Todos":
    df = df[df["sexo"] == sexo_sel]

# CONVOCATORIA comparte cohorte/programa/ciudad/grupo/sexo con V2_2026 --
# se le aplican los mismos filtros para que "Seleccionados"/"Pendientes
# por ingresar" respondan igual que el resto de la página.
df_conv = df_conv_full.copy()
if cohorte_sel != "Todas":
    df_conv = df_conv[df_conv["cohorte"] == cohorte_sel]
if programa_sel != "Todos":
    df_conv = df_conv[df_conv["programa"] == programa_sel]
if ciudad_sel != "Todas":
    df_conv = df_conv[df_conv["ciudad"] == ciudad_sel]
if grupo_sel != "Todos":
    df_conv = df_conv[df_conv["grupo"] == grupo_sel]
if sexo_sel != "Todos":
    df_conv = df_conv[df_conv["sexo"] == sexo_sel]

st.write("")

if df.empty:
    st.info("No hay registros para esta combinación de filtros.")
    st.stop()

kpis = kpis_overview(df)
kpis_conv = (
    kpis_convocatoria(df_conv)
    if not df_conv.empty
    else {"seleccionados": 0, "pendientes_por_ingresar": 0}
)

# ---------------------------------------------------------------------------
# Indicadores generales
# ---------------------------------------------------------------------------
st.subheader("Indicadores generales")
kpi_row(
    [
        ("Matriculados", str(kpis["matriculados"]), NARANJA, ""),
        ("Activos", str(kpis["activos"]), VERDE, ""),
        (
            "% Retención",
            f"{kpis['pct_retencion']:.1f}%",
            VERDE,
            "Activos / Matriculados",
        ),
        ("Deserciones", str(kpis["deserciones"]), ROJO, ""),
        (
            "% Deserción",
            f"{kpis['pct_desercion']:.1f}%",
            ROJO,
            "Deserciones / Matriculados",
        ),
    ]
)

st.write("")
kpi_row(
    [
        (
            "Seleccionados",
            str(kpis_conv["seleccionados"]),
            AMARILLO,
            "Candidatos de CONVOCATORIA con entrevista aprobada (Pasa/Repechaje)",
        ),
        (
            "Pendientes por ingresar",
            str(kpis_conv["pendientes_por_ingresar"]),
            AMARILLO,
            "Seleccionados que todavía no se matriculan",
        ),
        (
            "Finalizados",
            str(kpis["finalizados"]),
            AZUL,
            "≥8 módulos aprobados y fecha de finalización ya pasada",
        ),
        ("Grupos Activos", str(kpis["grupos_activos"]), AMARILLO, "COUNT(DISTINCT grupo)"),
        (
            "No Exitosas",
            f"{kpis['no_exitosas']} ({kpis['pct_no_exitosa']:.1f}%)",
            GRIS,
            "Matrículas que nunca se concretaron",
        ),
    ]
)

# ---------------------------------------------------------------------------
# Distribución
# ---------------------------------------------------------------------------
st.write("")
st.subheader("Distribución")
g1, g2, g3 = st.columns(3)

with g1, st.container(border=True):
    df_prog = grupos_por_programa(df)
    fig_prog = px.bar(
        df_prog,
        x="estudiantes",
        y="programa",
        orientation="h",
        title="Matriculados por Programa",
        text="estudiantes",
        color_discrete_sequence=[NARANJA],
        custom_data=["programa"],
    )
    fig_prog.update_layout(yaxis_title=None, xaxis_title=None)
    st.plotly_chart(
        dark(fig_prog),
        width="stretch",
        key="eco_chart_prog",
        on_select=click_to_filter("eco_chart_prog", "eco_programa_sel"),
        selection_mode="points",
    )

with g2, st.container(border=True):
    df_genero = genero_counts(df)
    fig_genero = px.pie(
        df_genero,
        names="sexo",
        values="cantidad",
        hole=0.55,
        title="Género",
        color_discrete_sequence=[NARANJA, AZUL, GRIS],
        custom_data=["sexo"],
    )
    fig_genero.update_traces(textinfo="value+percent")
    st.plotly_chart(
        dark(fig_genero),
        width="stretch",
        key="eco_chart_genero",
        on_select=click_to_filter("eco_chart_genero", "eco_sexo_sel"),
        selection_mode="points",
    )

with g3, st.container(border=True):
    df_ciudad = ciudad_counts(df)
    fig_ciudad = px.bar(
        df_ciudad,
        x="estudiantes",
        y="ciudad",
        orientation="h",
        title="Matriculados por Ciudad",
        text="estudiantes",
        color_discrete_sequence=[AZUL],
        custom_data=["ciudad"],
    )
    fig_ciudad.update_layout(yaxis_title=None, xaxis_title=None)
    st.plotly_chart(
        dark(fig_ciudad),
        width="stretch",
        key="eco_chart_ciudad",
        on_select=click_to_filter("eco_chart_ciudad", "eco_ciudad_sel"),
        selection_mode="points",
    )

# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------
st.write("")
st.subheader("Grupos")

df_grupos = tabla_grupos(df)

with st.container(border=True):
    fig_gantt = px.timeline(
        df_grupos,
        x_start="inicio",
        x_end="fin",
        y="grupo",
        color="programa",
        title="Cronograma de Grupos",
        hover_data=["ciudad", "estudiantes", "activos"],
    )
    fig_gantt.update_yaxes(autorange="reversed", title=None)
    st.plotly_chart(dark(fig_gantt, height=CHART_HEIGHT + 80), width="stretch")

with st.container(border=True):
    st.dataframe(
        df_grupos.rename(
            columns={
                "grupo": "Grupo",
                "programa": "Programa",
                "ciudad": "Ciudad",
                "inicio": "Inicio",
                "fin": "Fin",
                "estudiantes": "Estudiantes",
                "activos": "Activos",
            }
        ),
        width="stretch",
        hide_index=True,
    )
