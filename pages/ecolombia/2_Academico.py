"""
Ecolombia -- Académico.

Misma tabla y misma población base que Overview (ECOPLUS_V2_2026,
Activos/Deserciones/Retención idénticos) -- reutiliza
utils.ecolombia_metrics.enrich()/kpis_overview() en vez de duplicar esa
lógica. Lo propio de esta página (estado académico, Sankey, tabla de
módulos) vive en utils/ecolombia_academico_metrics.py -- ver ese archivo
para la justificación de cada fórmula, incluyendo la nota de aprobación
(>=3.0/5.0, confirmada con Christian) que usa la tabla de % por módulo.

Clic-para-filtrar: la barra "Estado Académico por Programa" y la barra
"Activos por Ciudad" tienen on_select -- el Sankey NO, porque no es una
gráfica de categoría simple (mismo criterio que excluyó el gantt de
Overview).
"""
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from queries.ecolombia.academico import get_academico_query
from utils.bigquery import run_query
from utils.ecolombia_academico_metrics import (
    ciudad_counts_activos,
    enrich_academico,
    estado_academico_por_programa,
    kpis_academico,
    sankey_modulos,
    tabla_modulo_aprobacion,
)
from utils.ecolombia_metrics import enrich, kpis_overview
from utils.ui import (
    AMARILLO,
    AZUL,
    GRIS,
    NARANJA,
    ROJO,
    VERDE,
    badge,
    click_to_filter,
    dark,
    hex_to_rgba,
    inject_css,
    kpi_row,
)

inject_css()

with st.spinner("Consultando BigQuery..."):
    df_raw = run_query(get_academico_query())

if df_raw.empty:
    st.warning("ECOPLUS_V2_2026 no devolvió filas. Revisa el acceso del Service Account.")
    st.stop()

df_full = enrich_academico(enrich(df_raw))

# ---------------------------------------------------------------------------
# Encabezado + filtros
# ---------------------------------------------------------------------------
col_title, col_badge = st.columns([5, 1], vertical_alignment="center")
col_title.title("Ecolombia -- Académico")
col_badge.markdown(badge(f"{len(df_full)} REGISTROS"), unsafe_allow_html=True)
st.caption("ECOPLUS_V2_2026 -- todas las cohortes, todos los programas")

TODOS = "Todos"

with st.container(border=True):
    f1, f2, f3, f4 = st.columns(4)
    cohortes = [TODOS] + sorted(df_full["cohorte"].dropna().unique().tolist())
    programas = [TODOS] + sorted(df_full["programa"].dropna().unique().tolist())
    ciudades = [TODOS] + sorted(df_full["ciudad"].dropna().unique().tolist())
    grupos = [TODOS] + sorted(df_full["grupo"].dropna().unique().tolist())

    cohorte_sel = f1.selectbox("Cohorte", cohortes, key="eco_acad_cohorte_sel")
    programa_sel = f2.selectbox("Programa", programas, key="eco_acad_programa_sel")
    ciudad_sel = f3.selectbox("Ciudad", ciudades, key="eco_acad_ciudad_sel")
    grupo_sel = f4.selectbox("Grupo", grupos, key="eco_acad_grupo_sel")

    f5, f6, f7 = st.columns(3)
    generos = [TODOS] + sorted(df_full["sexo"].dropna().unique().tolist())
    modulos_cursa = [TODOS] + sorted(df_full["modulo_que_cursa"].dropna().unique().tolist())
    resultados_acad = [TODOS] + sorted(df_full["_ESTADO_ACAD"].dropna().unique().tolist())

    sexo_sel = f5.selectbox("Género", generos, key="eco_acad_sexo_sel")
    modulo_cursa_sel = f6.selectbox(
        "Módulo que cursa", modulos_cursa, key="eco_acad_modulo_sel"
    )
    resultado_sel = f7.selectbox(
        "Resultados académicos", resultados_acad, key="eco_acad_resultado_sel"
    )

df = df_full.copy()
if cohorte_sel != TODOS:
    df = df[df["cohorte"] == cohorte_sel]
if programa_sel != TODOS:
    df = df[df["programa"] == programa_sel]
if ciudad_sel != TODOS:
    df = df[df["ciudad"] == ciudad_sel]
if grupo_sel != TODOS:
    df = df[df["grupo"] == grupo_sel]
if sexo_sel != TODOS:
    df = df[df["sexo"] == sexo_sel]
if modulo_cursa_sel != TODOS:
    df = df[df["modulo_que_cursa"] == modulo_cursa_sel]
if resultado_sel != TODOS:
    df = df[df["_ESTADO_ACAD"] == resultado_sel]

st.write("")

if df.empty:
    st.info("No hay registros para esta combinación de filtros.")
    st.stop()

kpis = kpis_overview(df)
kpis_acad = kpis_academico(df)

# ---------------------------------------------------------------------------
# Indicadores generales
# ---------------------------------------------------------------------------
st.subheader("Indicadores generales")
kpi_row(
    [
        ("Estudiantes Activos", str(kpis["activos"]), NARANJA, ""),
        (
            "Aprobados",
            str(kpis_acad["aprobados"]),
            AZUL,
            f"{kpis_acad['pct_aprobados']:.0f}% de {kpis_acad['calificables']} calificables",
        ),
        (
            "Deserción",
            f"{kpis['pct_desercion']:.2f}%",
            ROJO,
            f"{kpis['deserciones']} estudiantes",
        ),
        (
            "Retención",
            f"{kpis['pct_retencion']:.2f}%",
            VERDE,
            f"{kpis['activos']} estudiantes",
        ),
    ]
)

# ---------------------------------------------------------------------------
# Distribución
# ---------------------------------------------------------------------------
st.write("")
st.subheader("Distribución")
g1, g2 = st.columns(2)

with g1, st.container(border=True):
    df_estado_prog = estado_academico_por_programa(df)
    fig_estado_prog = px.bar(
        df_estado_prog,
        x="cantidad",
        y="programa",
        color="categoria",
        orientation="h",
        barmode="stack",
        title="Estado Académico por Programa",
        text="cantidad",
        color_discrete_map={
            "Al día académicamente": AZUL,
            "Con pendientes académicos": AMARILLO,
            "Pendientes por publicar nota": GRIS,
        },
        category_orders={
            "categoria": [
                "Al día académicamente",
                "Con pendientes académicos",
                "Pendientes por publicar nota",
            ]
        },
        custom_data=["categoria"],
    )
    fig_estado_prog.update_layout(yaxis_title=None, xaxis_title=None, legend_title_text="")
    st.plotly_chart(
        dark(fig_estado_prog),
        width="stretch",
        key="eco_acad_chart_estado",
        on_select=click_to_filter("eco_acad_chart_estado", "eco_acad_resultado_sel"),
        selection_mode="points",
    )

with g2, st.container(border=True):
    df_ciudad = ciudad_counts_activos(df)
    fig_ciudad = px.bar(
        df_ciudad,
        x="ciudad",
        y="estudiantes",
        title="Activos por Ciudad",
        text="estudiantes",
        color="ciudad",
        color_discrete_sequence=[NARANJA, AMARILLO, AZUL],
        custom_data=["ciudad"],
    )
    fig_ciudad.update_layout(showlegend=False, xaxis_title=None, yaxis_title=None)
    st.plotly_chart(
        dark(fig_ciudad),
        width="stretch",
        key="eco_acad_chart_ciudad",
        on_select=click_to_filter("eco_acad_chart_ciudad", "eco_acad_ciudad_sel"),
        selection_mode="points",
    )

# ---------------------------------------------------------------------------
# Módulos cursados -> aprobados
# ---------------------------------------------------------------------------
st.write("")
st.subheader("Módulos cursados → aprobados")

with st.container(border=True):
    sankey = sankey_modulos(df)
    if not sankey["value"]:
        st.info("No hay estudiantes activos con módulos cursados para esta combinación de filtros.")
    else:
        n_cursados = sankey["n_cursados"]
        n_aprobados = len(sankey["labels"]) - n_cursados
        # 2 grupos de nodos con color distinto (cursados vs aprobados) --
        # los links se pintan del color de su nodo de ORIGEN (cursados),
        # traslúcido, para que se vea el volumen del flujo.
        node_colors = [AZUL] * n_cursados + [VERDE] * n_aprobados
        link_colors = [hex_to_rgba(AZUL, 0.35) for _ in sankey["source"]]

        fig_sankey = go.Figure(
            go.Sankey(
                node=dict(
                    label=sankey["labels"],
                    color=node_colors,
                    pad=15,
                    thickness=16,
                ),
                link=dict(
                    source=sankey["source"],
                    target=sankey["target"],
                    value=sankey["value"],
                    color=link_colors,
                ),
            )
        )
        fig_sankey.update_layout(title="Flujo de módulos cursados a módulos aprobados")
        st.plotly_chart(dark(fig_sankey, height=380), width="stretch")

# ---------------------------------------------------------------------------
# % de aprobación por módulo
# ---------------------------------------------------------------------------
st.write("")
st.subheader("% de aprobación por módulo")

with st.container(border=True):
    df_tabla_mod = tabla_modulo_aprobacion(df)
    columnas_modulo = [c for c in df_tabla_mod.columns if c.startswith("Módulo")]
    st.dataframe(
        df_tabla_mod.style.format({c: "{:.2f}%" for c in columnas_modulo}, na_rep="—"),
        width="stretch",
        hide_index=True,
    )
