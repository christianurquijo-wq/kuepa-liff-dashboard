
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from queries.ecolombia.satisfaccion import get_satisfaccion_query
from utils.bigquery import run_query
from utils.ecolombia_empleabilidad_metrics import enrich_pool, resumen_estados
from utils.ecolombia_satisfaccion_metrics import (
    indicadores_por,
    kpis_satisfaccion,
    nps_ecolombia,
)
from utils.sheets import get_pool_empleabilidad
from utils.ui import (
    AMARILLO,
    AZUL,
    NARANJA,
    ROJO,
    VERDE,
    badge,
    dark,
    inject_css,
    kpi_row,
)

inject_css()

with st.spinner("Consultando BigQuery..."):
    df_raw = run_query(get_satisfaccion_query())

if df_raw.empty:
    st.warning("Satisfaccion_ECOPLUS_2026 no devolvió filas. Revisa el acceso del Service Account.")
    st.stop()

with st.spinner("Consultando Google Sheets (Activos)..."):
    df_pool_raw = get_pool_empleabilidad()

# ---------------------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------------------
col_title, col_badge = st.columns([5, 1], vertical_alignment="center")
col_title.title("Ecolombia -- Satisfacción")
col_badge.markdown(badge(f"{len(df_raw)} ENCUESTAS"), unsafe_allow_html=True)
st.caption("Satisfaccion_ECOPLUS_2026 -- Ecolombia 2.0")

kpis = kpis_satisfaccion(df_raw)
nps = nps_ecolombia(df_raw)
resumen_pool = resumen_estados(enrich_pool(df_pool_raw))

# ---------------------------------------------------------------------------
# KPIs generales
# ---------------------------------------------------------------------------
st.subheader("Indicadores generales")
kpi_row(
    [
        ("Encuestas", str(kpis["encuestas"]), NARANJA, "Total de respuestas -- Satisfaccion_ECOPLUS_2026"),
        ("Activos", str(resumen_pool["activos"]), AZUL, "Misma tarjeta que Pool de Empleabilidad"),
        (
            "NPS",
            f"{nps['pct']:.1f}%",
            VERDE if nps["pct"] >= 0 else ROJO,
            f"{nps['promotores']} promotores / {nps['neutros']} neutros / {nps['detractores']} detractores",
        ),
    ]
)

st.write("")
st.subheader("Evaluación por categoría")
kpi_row(
    [
        ("Evaluación docente", f"{kpis['Evaluación docente']:.2f}", AZUL, "Preguntas 1-4"),
        (
            "Recursos académicos",
            f"{kpis['Recursos académicos']:.2f}",
            AZUL,
            "Preguntas 5-9 -- el pantallazo de referencia mostraba 5; con la "
            "fórmula oficial de Christian el cálculo da esto. Pendiente de "
            "confirmar con el cliente, ver utils/ecolombia_satisfaccion_metrics.py.",
        ),
        ("Plataforma", f"{kpis['Plataforma']:.2f}", AZUL, "Preguntas 10-13"),
        ("Gestión Psicosocial", f"{kpis['Gestión Psicosocial']:.2f}", AZUL, "Preguntas 14-15"),
        ("Autoevaluación", f"{kpis['Autoevaluación']:.2f}", AZUL, "Pregunta 16"),
    ]
)

# ---------------------------------------------------------------------------
# Evaluación General + NPS
# ---------------------------------------------------------------------------
st.write("")
g1, g2 = st.columns(2)

with g1, st.container(border=True):
    fig_general = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=kpis["Evaluación General"],
            number={"valueformat": ".2f", "font": {"color": NARANJA}},
            gauge={
                "axis": {"range": [0, 5]},
                "bar": {"color": NARANJA},
            },
            title={"text": "Evaluación General"},
        )
    )
    st.plotly_chart(dark(fig_general), width="stretch")
    st.caption(
        "Promedio simple de los 5 indicadores de arriba -- sin fórmula "
        "oficial confirmada todavía (ver nota en utils/ecolombia_satisfaccion_metrics.py)."
    )

with g2, st.container(border=True):
    # Definición CLÁSICA (0..6 = detractor) -- es la que usa el donut del
    # pantallazo, distinta de la fórmula oficial de la tarjeta "NPS" de
    # arriba. Ver docstring de la página y de nps_ecolombia().
    df_nps = pd.DataFrame(
        {
            "Categoría": ["Promotor", "Neutro", "Detractor"],
            "Encuestas": [nps["promotores"], nps["neutros_donut"], nps["detractores_donut"]],
        }
    )
    fig_nps = px.pie(
        df_nps,
        names="Categoría",
        values="Encuestas",
        hole=0.55,
        title="NPS -- desglose (Promotor/Neutro/Detractor)",
        color="Categoría",
        color_discrete_map={"Promotor": VERDE, "Neutro": AMARILLO, "Detractor": ROJO},
    )
    fig_nps.update_traces(textinfo="value+percent")
    st.plotly_chart(dark(fig_nps), width="stretch")
    st.caption(
        "Detractor aquí = pregunta 0 a 6 (definición clásica, igual que el "
        "donut de Looker) -- distinta de la fórmula 1 a 6 que usa el % de "
        "la tarjeta 'NPS' de arriba. Las dos son correctas, cada una para "
        "lo que muestra -- ver nota en utils/ecolombia_satisfaccion_metrics.py."
    )

# ---------------------------------------------------------------------------
# Desglose por Grupo (barra agrupada + ranking) y por Programa
# ---------------------------------------------------------------------------
st.write("")
st.subheader("Desglose por Grupo")

df_por_grupo = indicadores_por(df_raw, "grupo")
INDICADORES_GRUPO = ["Evaluación docente", "Recursos académicos", "Plataforma", "Gestión Psicosocial"]

with st.container(border=True):
    df_grupo_largo = df_por_grupo.melt(
        id_vars="grupo", value_vars=INDICADORES_GRUPO, var_name="Indicador", value_name="Promedio"
    )
    fig_grupo = px.bar(
        df_grupo_largo,
        x="grupo",
        y="Promedio",
        color="Indicador",
        barmode="group",
        title="Evaluación docente / Recursos académicos / Plataforma / Gestión Psicosocial por Grupo",
        color_discrete_map={
            "Evaluación docente": AZUL,
            "Recursos académicos": ROJO,
            "Plataforma": AMARILLO,
            "Gestión Psicosocial": "#7E57C2",
        },
    )
    fig_grupo.update_layout(xaxis_title=None, yaxis_title=None)
    st.plotly_chart(dark(fig_grupo, height=380), width="stretch")

with st.container(border=True):
    df_ranking = df_por_grupo.sort_values("Evaluación General", ascending=False)
    fig_ranking = px.bar(
        df_ranking,
        x="grupo",
        y="Evaluación General",
        title="Ranking de Grupos -- promedio de los 4 indicadores",
        text_auto=".1f",
        color_discrete_sequence=[AZUL],
    )
    fig_ranking.update_layout(xaxis_title=None, yaxis_title=None)
    st.plotly_chart(dark(fig_ranking), width="stretch")

st.write("")
st.subheader("Desglose por Programa")
with st.container(border=True):
    df_por_programa = indicadores_por(df_raw, "programa_que_cursas")
    fig_programa = px.bar(
        df_por_programa.sort_values("Evaluación General", ascending=False),
        x="programa_que_cursas",
        y="Evaluación General",
        title="Evaluación General por Programa",
        text_auto=".2f",
        color_discrete_sequence=[AZUL],
    )
    fig_programa.update_layout(xaxis_title=None, yaxis_title=None)
    st.plotly_chart(dark(fig_programa), width="stretch")
    st.caption(
        "Validado contra el pantallazo: T.L en Auxiliar de Mercadeo y Ventas "
        "≈ 4.54, T.L en Procesamiento y Digitación ≈ 4.53, Técnico en "
        "Hotelería y Turismo ≈ 4.31 -- confirma la fórmula al correr la página."
    )
