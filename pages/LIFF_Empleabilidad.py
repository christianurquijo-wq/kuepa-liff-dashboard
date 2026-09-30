"""
LIFF -- Empleabilidad.

oct-2026: primera versión. Fuente y reglas de negocio completas en
utils/liff_empleabilidad_metrics.py (léelo antes de tocar esta página --
ahí está la auditoría de calidad de datos que explica cada filtro).

Privacidad: igual regla que el resto del dashboard (ver utils/iq_metrics.py
regla 2) -- nunca se muestra Nombre/Correo/Teléfono/Documento en esta
página, solo agregados.
"""
import plotly.express as px
import streamlit as st

from utils.liff_empleabilidad_metrics import (
    empresas_top,
    enrich,
    funnel_poblacion,
    kpis_poblacion,
    resumen_por_dimension_poblacion,
    salidas_poblacion,
    tiempos_poblacion,
)
from utils.sheets import get_base_postulaciones
from utils.ui import AMARILLO, AZUL, NARANJA, ROJO, VERDE, badge, dark, inject_css, kpi_row

inject_css()

with st.spinner("Consultando Google Sheets..."):
    df_raw = get_base_postulaciones()

if df_raw.empty:
    st.warning(
        "La pestaña 'Base postulaciones' no devolvió filas. Revisa que la hoja esté "
        "compartida como Viewer con el Service Account."
    )
    st.stop()

df = enrich(df_raw)

col_title, col_badge = st.columns([5, 1], vertical_alignment="center")
col_title.title("LIFF -- Empleabilidad")
col_badge.markdown(badge(f"{len(df)} REGISTROS"), unsafe_allow_html=True)
st.caption(
    "Base postulaciones, cohortes desde agosto 2026 -- misma línea de tiempo que el resto de "
    "LIFF Data. Comparaciones Extranjeros vs Nacionales en % del total de cada población (no "
    "del combinado), igual criterio que el resto del dashboard."
)

if df.empty:
    st.info("No hay filas de LIFF con Cohorte desde agosto 2026 en 'Base postulaciones'.")
    st.stop()

n_sin_clasificar = int(df["_POBLACION"].isna().sum())
if n_sin_clasificar:
    st.caption(
        f"{n_sin_clasificar} estudiante(s) sin Tipo de documento reconocible -- "
        "quedan fuera de las comparaciones Extranjeros/Nacionales."
    )

kpis = kpis_poblacion(df)

# ---------------------------------------------------------------------------
# KPIs -- X vs Y (Extranjeros vs Nacionales)
# ---------------------------------------------------------------------------
st.subheader("Extranjeros vs Nacionales")
kpi_row(
    [
        (
            "Total en Empleabilidad",
            f"{kpis['total']['Extranjeros']} vs {kpis['total']['Nacionales']}",
            AZUL,
            "Extranjeros vs Nacionales",
        ),
        (
            "Contratados/Patrocinados",
            f"{kpis['contratados']['Extranjeros']} vs {kpis['contratados']['Nacionales']}",
            VERDE,
            "Aprobado/Patrocinado + Otro tipo de contrato",
        ),
        (
            "En pool (activos)",
            f"{kpis['en_pool']['Extranjeros']} vs {kpis['en_pool']['Nacionales']}",
            AMARILLO,
            "sin proceso / En Proceso / Carta de presentación / Proceso Avanzado",
        ),
        (
            "Salidas",
            f"{kpis['salida']['Extranjeros']} vs {kpis['salida']['Nacionales']}",
            ROJO,
            "Baja + Matricula no Exitosa + Prospecto Caido + No patrocinable",
        ),
    ]
)

# ---------------------------------------------------------------------------
# Funnel de postulación a contratación
# ---------------------------------------------------------------------------
st.write("")
st.subheader("Funnel de postulación a contratación")
st.caption("Cada barra es el % del total DE ESA población (no del total combinado).")

df_funnel = funnel_poblacion(df)
if df_funnel.empty:
    st.info("No hay datos suficientes para el funnel.")
else:
    fig = px.bar(
        df_funnel, x="etapa", y="porcentaje", color="poblacion", barmode="group",
        title="Etapa del proceso (%)",
        color_discrete_map={"Extranjeros": NARANJA, "Nacionales": AZUL},
        category_orders={"etapa": df_funnel["etapa"].drop_duplicates().tolist()},
        text=df_funnel["porcentaje"].round(1).astype(str) + "%",
        custom_data=["cantidad"],
    )
    fig.update_traces(hovertemplate="%{x}: %{y:.1f}% (%{customdata[0]} estudiantes)<extra>%{fullData.name}</extra>")
    fig.update_layout(xaxis_title=None, yaxis_title="% de la población", legend_title=None)
    st.plotly_chart(dark(fig), width="stretch", key="emp_chart_funnel")

df_salidas = salidas_poblacion(df)
if not df_salidas.empty:
    with st.expander("Ver estados de salida (Baja / No exitosa / Prospecto caído / No patrocinable)"):
        st.caption(
            "Se muestran aparte del funnel porque pueden ocurrir desde cualquier etapa -- "
            "no son 'el paso siguiente' de una progresión lineal."
        )
        fig_salidas = px.bar(
            df_salidas, x="estado", y="porcentaje", color="poblacion", barmode="group",
            title="Estados de salida (%)",
            color_discrete_map={"Extranjeros": NARANJA, "Nacionales": AZUL},
            text=df_salidas["porcentaje"].round(1).astype(str) + "%",
            custom_data=["cantidad"],
        )
        fig_salidas.update_traces(hovertemplate="%{x}: %{y:.1f}% (%{customdata[0]} estudiantes)<extra>%{fullData.name}</extra>")
        fig_salidas.update_layout(xaxis_title=None, yaxis_title="% de la población", legend_title=None)
        st.plotly_chart(dark(fig_salidas), width="stretch", key="emp_chart_salidas")

# ---------------------------------------------------------------------------
# Tiempos
# ---------------------------------------------------------------------------
st.write("")
st.subheader("Tiempos")

df_tiempos = tiempos_poblacion(df)
if df_tiempos.empty:
    st.info("No hay datos de tiempos disponibles.")
else:
    g1, g2 = st.columns(2)
    for col, metrica in zip((g1, g2), df_tiempos["metrica"].unique()):
        with col, st.container(border=True):
            sub = df_tiempos[df_tiempos["metrica"] == metrica]
            fig_t = px.bar(
                sub, x="poblacion", y="promedio", color="poblacion",
                title=metrica,
                color_discrete_map={"Extranjeros": NARANJA, "Nacionales": AZUL},
                text=sub["promedio"].round(1),
                custom_data=["mediana", "n"],
            )
            fig_t.update_traces(
                hovertemplate="%{x}: promedio %{y:.1f} días (mediana %{customdata[0]:.1f}, n=%{customdata[1]})<extra></extra>"
            )
            fig_t.update_layout(xaxis_title=None, yaxis_title="Días (promedio)", showlegend=False)
            st.plotly_chart(dark(fig_t, height=260), width="stretch", key=f"emp_chart_tiempo_{metrica}")

# ---------------------------------------------------------------------------
# Empresas patrocinadoras
# ---------------------------------------------------------------------------
st.write("")
st.subheader("Empresas patrocinadoras")
df_empresas = empresas_top(df, top=15)
if df_empresas.empty:
    st.info("No hay datos de empresa patrocinadora.")
else:
    with st.container(border=True):
        fig_emp = px.bar(
            df_empresas.sort_values("estudiantes"), x="estudiantes", y="empresa", orientation="h",
            title="Top empresas por estudiantes asociados",
            color="pct_aprobacion", color_continuous_scale=["#8C8C8C", VERDE],
            custom_data=["pct_aprobacion", "aprobados"],
        )
        fig_emp.update_traces(
            hovertemplate="%{y}: %{x} estudiantes, %{customdata[0]:.1f}% patrocinados (%{customdata[1]})<extra></extra>"
        )
        fig_emp.update_layout(yaxis_title=None, xaxis_title="Estudiantes", coloraxis_colorbar_title="% patrocinado")
        st.plotly_chart(dark(fig_emp, height=420), width="stretch", key="emp_chart_empresas")
    st.caption(
        "% patrocinado = de los estudiantes asociados a esa empresa, cuántos están HOY en "
        "'Aprobado/Patrocinado' -- es el estado actual del estudiante, no el resultado de "
        "esa postulación puntual (un estudiante puede haber pasado por varias empresas)."
    )

# ---------------------------------------------------------------------------
# Por programa / asesor
# ---------------------------------------------------------------------------
st.write("")
st.subheader("Por programa / asesor")
dim_sel = st.radio("Desglosar por", ["Programa", "Asesor"], horizontal=True, key="emp_dim_sel")
columna_dim = "Programa " if dim_sel == "Programa" else "Asesor"

df_dim = resumen_por_dimension_poblacion(df, columna_dim)
if df_dim.empty:
    st.info("No hay datos suficientes para este desglose.")
else:
    g3, g4 = st.columns(2)
    with g3, st.container(border=True):
        fig_dim = px.bar(
            df_dim, x="pct_estudiantes", y=columna_dim, color="poblacion", orientation="h", barmode="group",
            title=f"Estudiantes por {dim_sel} (% de cada población)",
            color_discrete_map={"Extranjeros": NARANJA, "Nacionales": AZUL},
            custom_data=["estudiantes"],
        )
        fig_dim.update_traces(hovertemplate="%{y}: %{x:.1f}% (%{customdata[0]} estudiantes)<extra>%{fullData.name}</extra>")
        fig_dim.update_layout(yaxis_title=None, xaxis_title="% de la población", legend_title=None)
        st.plotly_chart(dark(fig_dim, height=380), width="stretch", key="emp_chart_dim_estudiantes")
    with g4, st.container(border=True):
        fig_contrat = px.bar(
            df_dim, x="pct_contratacion", y=columna_dim, color="poblacion", orientation="h", barmode="group",
            title=f"% Contratación por {dim_sel}",
            color_discrete_map={"Extranjeros": NARANJA, "Nacionales": AZUL},
            custom_data=["estudiantes"],
        )
        fig_contrat.update_traces(hovertemplate="%{y}: %{x:.1f}% contratación (%{customdata[0]} estudiantes)<extra>%{fullData.name}</extra>")
        fig_contrat.update_layout(yaxis_title=None, xaxis_title="% Contratación dentro de esa categoría", legend_title=None)
        st.plotly_chart(dark(fig_contrat, height=380), width="stretch", key="emp_chart_dim_contratacion")
