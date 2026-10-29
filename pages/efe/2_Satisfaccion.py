"""
EFE General › Satisfacción -- migrado de la pestaña "Satisfacción" de «Dash General EFE2» (n8n).

Fuente: vista EFE_2026.Unificado_Satisfaccion (una fila por encuesta respondida).
NPS estándar: % promotores (9–10) − % detractores (0–6). Meta de satisfacción: 4,5.
Nota: Institución y "¿Recomienda para empleabilidad?" no se preguntan en Ecolombia ni en
Jóvenes a la E; Psicosocial y Autoevaluación solo en esos dos. Los promedios ignoran vacíos.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from utils import efe_data as data
from utils import efe_metrics as m
from utils.efe_ui import TODOS, aplicar, barras, dona, filtro, inicio
from utils.ui import AMARILLO, AZUL, GRIS, NARANJA, ROJO, VERDE, dark, kpi_row

inicio("EFE · Satisfacción", "Encuestas de satisfacción y NPS · fuente: Unificado_Satisfaccion")

with st.spinner("Consultando BigQuery..."):
    base = data.satisfaccion()
if base.empty:
    st.warning("Unificado_Satisfaccion no devolvió filas.")
    st.stop()

c1, c2 = st.columns([1, 1.6])
proyecto = filtro(base, "Proyecto", "Proyecto", "efe_sat_proy", c1)
df = aplicar(base, "Proyecto", proyecto)
fechas = df["fecha"].dropna()
if not fechas.empty:
    rango = c2.date_input("Fecha de la encuesta", value=(fechas.min().date(), fechas.max().date()),
                          min_value=fechas.min().date(), max_value=fechas.max().date(), key="efe_sat_fechas",
                          format="DD/MM/YYYY")
    sin_fecha = int(df["fecha"].isna().sum())
    if isinstance(rango, (list, tuple)) and len(rango) == 2:  # mientras eliges, llega 1 sola fecha
        df = df[df["fecha"].isna() | df["fecha"].between(pd.Timestamp(rango[0]), pd.Timestamp(rango[1]))]
    if sin_fecha:
        c2.caption(f"{sin_fecha:,} encuestas sin fecha se incluyen siempre.")

k = m.kpis_satisfaccion(df)
color_sat = VERDE if (k["satisfaccion"] or 0) >= m.META_SATISFACCION else AMARILLO
kpi_row([
    ("Muestra", m.fmt_num(k["muestra"]), GRIS, "Encuestas respondidas"),
    ("Satisfacción general", m.fmt_num(k["satisfaccion"], 2), color_sat, f"Meta {m.META_SATISFACCION}".replace(".", ",")),
    ("NPS", m.fmt_num(k["nps"], 1), NARANJA, "% promotores − % detractores"),
    ("Docente", m.fmt_num(k["Docente"], 2), AZUL, "Promedio 1–5"),
])
st.write("")
kpi_row([
    ("Contenidos", m.fmt_num(k["Contenidos"], 2), AZUL, ""),
    ("Institución", m.fmt_num(k["Institución"], 2), AZUL, "No aplica a Ecolombia / JaE"),
    ("Plataforma", m.fmt_num(k["Plataforma"], 2), AZUL, ""),
    ("Psicosocial", m.fmt_num(k["Psicosocial"], 2), AZUL, "Solo Ecolombia / JaE"),
])

st.divider()
col_a, col_b = st.columns(2)
with col_a:
    dims = pd.DataFrame([{"Categoría": n, "Promedio": k[n]} for n in m.DIMENSIONES_SAT if k[n] is not None])
    if not dims.empty:
        dims["Promedio"] = dims["Promedio"].round(2)
    barras(dims, "Categoría", "Promedio", "Desempeño por categoría (1–5)", range_y=[0, 5.4])
with col_b:
    dona(m.nps_categoria(df["NPS"]).value_counts().reindex(["Promotor (9–10)", "Pasivo (7–8)", "Detractor (0–6)"]),
         "Distribución NPS", colores={"Promotor (9–10)": VERDE, "Pasivo (7–8)": AMARILLO, "Detractor (0–6)": ROJO})

col_c, col_d = st.columns(2)
with col_c:
    por_proy = (df.groupby("Proyecto").agg(Satisfacción=("Promedio_Satisfaccion", "mean"),
                                           NPS=("NPS", m.nps), Muestra=("NPS", "size")).reset_index())
    if not por_proy.empty:
        por_proy["Satisfacción"] = por_proy["Satisfacción"].round(2)
        fig = px.bar(por_proy, x="Proyecto", y="Satisfacción", text="Satisfacción", title="Satisfacción vs meta (4,5)",
                     color_discrete_sequence=[NARANJA], range_y=[0, 5.4])
        fig.add_hline(y=m.META_SATISFACCION, line_dash="dash", line_color=VERDE, annotation_text="Meta 4,5")
        fig.update_traces(textposition="outside")
        st.plotly_chart(dark(fig, 340), use_container_width=True)
with col_d:
    dona(df["recomienda_empleabilidad"].value_counts(), "¿El curso aporta a tu empleabilidad?",
         colores={"Sí": VERDE, "No": ROJO})

if proyecto == TODOS and not por_proy.empty:
    st.subheader("Comparativo por proyecto")
    por_proy["NPS"] = por_proy["NPS"].round(1)
    st.dataframe(por_proy, hide_index=True, use_container_width=True)
