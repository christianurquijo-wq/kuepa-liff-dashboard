
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.ecolombia_empleabilidad_metrics import (
    HISTORICO_SERIES,
    combo_procesos,
    enrich_pool,
    historico_pool,
    postulaciones_realizadas,
    programa_pool,
    promedio_dias_pool,
    resumen_estados,
)
from utils.sheets import get_historico_empleabilidad, get_pool_empleabilidad
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

with st.spinner("Consultando Google Sheets..."):
    df_raw = get_pool_empleabilidad()

if df_raw.empty:
    st.warning(
        "La pestaña 'TiempoEnPool' no devolvió filas. Revisa que la hoja "
        "esté compartida como Viewer con el Service Account."
    )
    st.stop()

df_full = enrich_pool(df_raw)

# ---------------------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------------------
col_title, col_badge = st.columns([5, 1], vertical_alignment="center")
col_title.title("Ecolombia -- Pool de Empleabilidad")
col_badge.markdown(badge(f"{len(df_full)} REGISTROS"), unsafe_allow_html=True)
st.caption("TiempoEnPool (Cohorte = ECOLOMBIA) -- estados del proceso de patrocinio/empleabilidad")

if df_full.empty:
    st.info("No hay filas con Cohorte == 'ECOLOMBIA' en esta pestaña.")
    st.stop()

resumen = resumen_estados(df_full)
pool_prom = promedio_dias_pool(df_full)
pool_post = postulaciones_realizadas(df_full)
df_programa = programa_pool(df_full)
estudiantes_en_pool = int(df_programa["estudiantes"].sum())

# ---------------------------------------------------------------------------
# KPIs -- estados del pool
# ---------------------------------------------------------------------------
st.subheader("Estados del pool")
kpi_row(
    [
        (
            "Contratados",
            str(resumen["contratados"]),
            VERDE,
            "Aprobado/Patrocinado + Otro tipo de contrato",
        ),
        (
            "Matrículas no exitosas",
            str(resumen["no_exitosa"]),
            ROJO,
            "Estado Patrocinio = Matricula no Exitosa",
        ),
        (
            "No patrocinable",
            str(resumen["no_patrocinable"]),
            ROJO,
            "Estado Patrocinio = No patrocinable",
        ),
        (
            "Sin proceso",
            str(resumen["sin_proceso"]),
            AMARILLO,
            f"{resumen['pct_sin_proceso']:.1f}% de {resumen['activos']} Activos",
        ),
        (
            "Activos",
            str(resumen["activos"]),
            AZUL,
            "Total - Matrículas no exitosas - Baja",
        ),
    ]
)

st.write("")
st.subheader("Pool")
kpi_row(
    [
        (
            "Estudiantes en pool",
            str(estudiantes_en_pool),
            NARANJA,
            "Carta de presentación / Caso especial / En Proceso / Otro tipo de "
            "contrato / Proceso Avanzado / sin proceso (ver metrics.py)",
        ),
        (
            "Promedio de días en el pool",
            f"{pool_prom:.1f}",
            AZUL,
            "Promedio de \"Tiempo en el Pool\" sobre todo Ecolombia+2026",
        ),
        (
            "Postulaciones realizadas",
            f"{pool_post:,}",
            VERDE,
            "Suma de \"cantidad de proceso\" sobre todo Ecolombia+2026",
        ),
    ]
)

# ---------------------------------------------------------------------------
# Donut por Programa + combo de procesos
# ---------------------------------------------------------------------------
st.write("")
g1, g2 = st.columns(2)

with g1, st.container(border=True):
    fig_donut = px.pie(
        df_programa,
        names="Programa",
        values="estudiantes",
        hole=0.55,
        title=f"Pool por Programa ({estudiantes_en_pool} estudiantes)",
        color_discrete_sequence=[NARANJA, AZUL, VERDE],
    )
    fig_donut.update_traces(textinfo="value+percent")
    st.plotly_chart(dark(fig_donut), width="stretch")

with g2, st.container(border=True):
    df_combo = combo_procesos(df_full)
    if df_combo.empty:
        st.info("No hay datos de 'cantidad de proceso' para graficar el combo.")
    else:
        fig_combo = go.Figure()
        fig_combo.add_bar(
            x=df_combo["cantidad de proceso"],
            y=df_combo["estudiantes"],
            name="Estudiantes",
            marker_color=AZUL,
        )
        fig_combo.add_trace(
            go.Scatter(
                x=df_combo["cantidad de proceso"],
                y=df_combo["promedio_tiempo_pool"],
                name="Promedio días en el pool",
                mode="lines+markers",
                yaxis="y2",
                line=dict(color=NARANJA, width=3),
            )
        )
        fig_combo.update_layout(
            title="Cantidad de procesos por estudiante x Tiempo en el Pool",
            xaxis_title="Cantidad de proceso",
            yaxis=dict(title="Estudiantes"),
            yaxis2=dict(title="Días en el pool (promedio)", overlaying="y", side="right"),
        )
        st.plotly_chart(dark(fig_combo), width="stretch")

# ---------------------------------------------------------------------------
# Histórico
# ---------------------------------------------------------------------------
st.write("")
st.subheader("Histórico")

with st.spinner("Consultando 'Histórico'..."):
    df_historico_raw = get_historico_empleabilidad()

with st.container(border=True):
    df_hist = historico_pool(df_historico_raw)
    if df_hist.empty:
        st.info("No hay filas con Cohorte == 'ECOLOMBIA' en la pestaña 'Histórico'.")
    else:
        colores_series = {
            "Contratados": VERDE,
            "En ruta de Empleabilidad": AZUL,
            "En proceso": NARANJA,
            "Carta de presentación": AMARILLO,
            "Sin proceso": ROJO,
        }
        fig_hist = px.line(
            df_hist,
            x="Fecha",
            y=list(HISTORICO_SERIES.keys()),
            markers=True,
            title=f"{df_hist['Fecha'].min():%d-%b} a {df_hist['Fecha'].max():%d-%b-%Y}",
            color_discrete_map=colores_series,
        )
        fig_hist.update_layout(xaxis_title=None, yaxis_title=None, legend_title_text="")
        st.plotly_chart(dark(fig_hist), width="stretch")
        st.caption(
            "Se descartan duplicados de carga por (Id CRM, DiaAppend) antes de "
            "graficar -- ver docstring de historico_pool() en "
            "utils/ecolombia_empleabilidad_metrics.py."
        )
