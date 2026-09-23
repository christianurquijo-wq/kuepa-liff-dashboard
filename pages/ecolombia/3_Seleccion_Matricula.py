
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from queries.ecolombia.convocatoria import get_convocatoria_query
from utils.bigquery import run_query
from utils.ecolombia_seleccion_metrics import (
    META_MATRICULADOS_DEFAULT,
    aliado_referido_ranking,
    avance_metas,
    enrich_seleccion,
    funnel_arbol,
    historico_matriculas,
    historico_preinscritos,
    sankey_convocatoria,
)
from utils.ui import (
    AMARILLO,
    AZUL,
    GRIS,
    NARANJA,
    ROJO,
    VERDE,
    badge,
    dark,
    hex_to_rgba,
    inject_css,
    kpi_row,
)

inject_css()

with st.spinner("Consultando BigQuery..."):
    df_raw = run_query(get_convocatoria_query())

if df_raw.empty:
    st.warning("ECOPLUS_2026_CONVOCATORIA no devolvió filas. Revisa el acceso del Service Account.")
    st.stop()

df_full = enrich_seleccion(df_raw)

# ---------------------------------------------------------------------------
# Encabezado + filtros
# ---------------------------------------------------------------------------
col_title, col_badge = st.columns([5, 1], vertical_alignment="center")
col_title.title("Ecolombia -- Selección y Matrícula")
col_badge.markdown(badge(f"{len(df_full)} REGISTROS"), unsafe_allow_html=True)
st.caption("ECOPLUS_2026_CONVOCATORIA -- embudo completo de candidatos (preinscripción a matrícula)")

TODOS = "Todos"

with st.container(border=True):
    f1, f2, f3, f4, f5 = st.columns([1, 1, 1, 1.4, 1.2])
    adnetworks = [TODOS] + sorted(df_full["adnetwork"].dropna().unique().tolist())
    ciudades = [TODOS] + sorted(df_full["ciudad"].dropna().unique().tolist())
    resultados = [TODOS] + sorted(df_full["resultado_entrevista"].dropna().unique().tolist())
    aliados = [TODOS] + sorted(df_full["aliado__referido"].dropna().unique().tolist())

    adnetwork_sel = f1.selectbox("Adnetwork", adnetworks, key="eco_sel_adnetwork_sel")
    ciudad_sel = f2.selectbox("Ciudad", ciudades, key="eco_sel_ciudad_sel")
    resultado_sel = f3.selectbox("Resultado entrevista", resultados, key="eco_sel_resultado_sel")
    aliado_sel = f4.selectbox("Aliado / Referido", aliados, key="eco_sel_aliado_sel")
    meta_matriculados = f5.number_input(
        "Meta de matrículas",
        min_value=1,
        value=META_MATRICULADOS_DEFAULT,
        step=1,
        key="eco_sel_meta_matriculados",
        help="Meta de matrículas efectivas de esta convocatoria -- ajústala aquí cuando cambie, sin tocar código.",
    )

df = df_full.copy()
if adnetwork_sel != TODOS:
    df = df[df["adnetwork"] == adnetwork_sel]
if ciudad_sel != TODOS:
    df = df[df["ciudad"] == ciudad_sel]
if resultado_sel != TODOS:
    df = df[df["resultado_entrevista"] == resultado_sel]
if aliado_sel != TODOS:
    df = df[df["aliado__referido"] == aliado_sel]

st.write("")

if df.empty:
    st.info("No hay registros para esta combinación de filtros.")
    st.stop()

arbol = funnel_arbol(df)
metas = avance_metas(df, meta_matriculados=int(meta_matriculados))

# ---------------------------------------------------------------------------
# Avance hacia la meta
# ---------------------------------------------------------------------------
st.subheader("Avance hacia la meta")
kpi_row(
    [
        (
            "Avance de Selección",
            f"{metas['pct_avance_seleccion']:.1f}%",
            AMARILLO,
            f"{metas['seleccionados']} / {metas['meta_entrevistas'] or '—'} entrevistas necesarias",
        ),
        (
            "Avance de Matriculación",
            f"{metas['pct_avance_matriculacion']:.1f}%",
            VERDE,
            f"{metas['matriculados']} / {metas['meta_matriculados']} matrículas meta",
        ),
        (
            "Leads necesarios",
            str(metas["leads_necesarios"]),
            AZUL,
            "Para llegar a la meta con las tasas de conversión actuales (±1 por redondeo)",
        ),
        (
            "Proyección requisitos",
            str(metas["proyeccion_requisitos"]),
            AZUL,
            "Candidatos que deben cumplir requisitos para llegar a la meta",
        ),
        (
            "Matrículas pendientes",
            str(metas["matriculas_pendientes"]),
            NARANJA,
            "Meta - Matriculados",
        ),
    ]
)

st.write("")
p1, p2 = st.columns(2)
with p1:
    st.markdown(
        f"{badge('PENDIENTE', GRIS)} **Retención** -- falta confirmar la definición exacta "
        "post-matrícula para esta tabla (podría vivir en V2_2026).",
        unsafe_allow_html=True,
    )
with p2:
    st.markdown(
        f"{badge('PENDIENTE', GRIS)} **Ritmo (gauge 103%)** -- falta confirmar fecha de "
        "arranque/cierre de la convocatoria para calcularlo.",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Embudo completo
# ---------------------------------------------------------------------------
st.write("")
st.subheader("Embudo completo")

with st.container(border=True):
    sankey = sankey_convocatoria(df)
    color_por_nodo = {
        "Usuarios": GRIS,
        "Descartados": ROJO,
        "Cumple requisitos": AZUL,
        "Agendados": AMARILLO,
        "Seleccionado": VERDE,
        "Repechaje": VERDE,
        "No Pasa": ROJO,
        "Matriculado": VERDE,
        "Pendiente Contrato": AMARILLO,
        "Retiro": ROJO,
        "En proceso de matrícula": AMARILLO,
        "Pendiente": GRIS,
    }
    node_colors = [color_por_nodo.get(label, GRIS) for label in sankey["labels"]]
    link_colors = [hex_to_rgba(node_colors[s], 0.35) for s in sankey["source"]]

    fig_sankey = go.Figure(
        go.Sankey(
            node=dict(label=sankey["labels"], color=node_colors, pad=15, thickness=16),
            link=dict(
                source=sankey["source"],
                target=sankey["target"],
                value=sankey["value"],
                color=link_colors,
            ),
        )
    )
    fig_sankey.update_layout(title="Usuarios → Requisitos → Entrevista → Matrícula")
    st.plotly_chart(dark(fig_sankey, height=460), width="stretch")

st.caption(
    f"Usuarios {arbol['usuarios']} · Descartados {arbol['descartados']} · "
    f"Cumple requisitos {arbol['cumple_requisitos']} · Agendados {arbol['agendados']} · "
    f"Seleccionado {arbol['seleccionado']} · Repechaje {arbol['repechaje']} · "
    f"No Pasa {arbol['no_pasa']}"
)

# ---------------------------------------------------------------------------
# Aliado / Referido
# ---------------------------------------------------------------------------
st.write("")
st.subheader("Aliado / Referido")

with st.container(border=True):
    df_aliados = aliado_referido_ranking(df, top_n=15)
    st.dataframe(df_aliados, width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Históricos
# ---------------------------------------------------------------------------
st.write("")
st.subheader("Históricos")
h1, h2 = st.columns(2)

with h1, st.container(border=True):
    df_hist_matriculas = historico_matriculas(df)
    if df_hist_matriculas.empty:
        st.info("No hay fechas de matrícula para esta combinación de filtros.")
    else:
        fig_hist_matriculas = px.line(
            df_hist_matriculas,
            x="fecha",
            y="acumulado",
            title="Histórico acumulado de matrículas",
            markers=True,
            color_discrete_sequence=[VERDE],
        )
        fig_hist_matriculas.update_layout(xaxis_title=None, yaxis_title=None)
        st.plotly_chart(dark(fig_hist_matriculas), width="stretch")

with h2, st.container(border=True):
    df_hist_preinscritos = historico_preinscritos(df)
    if df_hist_preinscritos.empty:
        st.info("No hay fechas de preinscripción para esta combinación de filtros.")
    else:
        fig_hist_preinscritos = px.line(
            df_hist_preinscritos,
            x="fecha",
            y="personas",
            title="Preinscritos por día",
            markers=True,
            color_discrete_sequence=[NARANJA],
        )
        fig_hist_preinscritos.update_layout(xaxis_title=None, yaxis_title=None)
        st.plotly_chart(dark(fig_hist_preinscritos), width="stretch")
