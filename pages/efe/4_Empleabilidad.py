"""
EFE General › Empleabilidad -- migrado de la pestaña "Empleabilidad" de «Dash General EFE2».

Fuente: vista EFE_2026.Unificado_Empleabilidad (Suba es Oportunidad, Ecolombia 2.0 y
Jóvenes a la E). Contratados = Contratado + Colocado. Postulaciones = suma de
Total_remisiones_postulaciones (los valores no numéricos, p. ej. "Retiro", no suman).
"""
import plotly.express as px
import streamlit as st

from utils import efe_data as data
from utils import efe_metrics as m
from utils.efe_ui import PALETA, TODOS, aplicar, barras, dona, filtro, inicio
from utils.ui import AMARILLO, AZUL, GRIS, ROJO, VERDE, dark, kpi_row

inicio("EFE · Empleabilidad", "Postulaciones y contratación · fuente: Unificado_Empleabilidad")

with st.spinner("Consultando BigQuery..."):
    base = data.empleabilidad()
if base.empty:
    st.warning("Unificado_Empleabilidad no devolvió filas.")
    st.stop()

c1, c2, _ = st.columns([1, 1, 1])
proyecto = filtro(base, "Proyecto", "Proyecto", "efe_emp_proy", c1)
df = aplicar(base, "Proyecto", proyecto)
ciudad = filtro(df, "Ciudad", "Ciudad", "efe_emp_ciudad", c2)
df = aplicar(df, "Ciudad", ciudad)

k = m.kpis_empleabilidad(df)
kpi_row([
    ("Participantes", m.fmt_num(k["participantes"]), GRIS, ""),
    ("Activos", m.fmt_num(k["activos"]), AZUL, "Estado académico Activo"),
    ("Deserción", m.fmt_pct(k["desercion"]), ROJO, "Retiro + Expulsado ÷ participantes"),
    ("Postulaciones", m.fmt_num(k["postulaciones"]), AMARILLO, "Remisiones / postulaciones"),
    ("Contratados", m.fmt_num(k["contratados"]), VERDE, f"Colocación {m.fmt_pct(k['colocacion'])}"),
])

st.divider()
colores = {"Contratado": VERDE, "Colocado": "#1E8449", "Postulado": AMARILLO, "Otros": GRIS,
           "Sin proceso": AZUL, "No disponible": ROJO}
col_a, col_b = st.columns([1.4, 1])
with col_a:
    por_ciudad = (df.groupby(["Ciudad", "Estado_contratacion"])["Documento"].nunique()
                  .rename("Personas").reset_index())
    if por_ciudad.empty:
        st.info("Sin datos para este filtro.")
    else:
        fig = px.bar(por_ciudad, x="Ciudad", y="Personas", color="Estado_contratacion", text="Personas",
                     title="Estado de contratación por ciudad", color_discrete_map=colores,
                     color_discrete_sequence=PALETA)
        st.plotly_chart(dark(fig, 360), use_container_width=True)
with col_b:
    dona(df.drop_duplicates(["Documento", "Proyecto"])["Estado_contratacion"].value_counts(),
         "Distribución general de procesos", colores=colores)

col_c, col_d = st.columns(2)
with col_c:
    post = df["postulaciones"].dropna().astype(int).value_counts().sort_index().rename_axis("Postulaciones")
    barras(post.rename("Personas").reset_index().astype({"Postulaciones": str}), "Postulaciones", "Personas",
           "Personas según número de postulaciones")
with col_d:
    emp = df.dropna(subset=["Empresa"])
    top = emp[emp["contratado"]].groupby("Empresa")["Documento"].nunique().nlargest(10).rename("Contratados")
    barras(top.reset_index(), "Empresa", "Contratados", "Top 10 empresas que contratan", horizontal=True)

if proyecto == TODOS:
    st.subheader("Comparativo por proyecto")
    filas = []
    for p, x in df.groupby("Proyecto"):
        kp = m.kpis_empleabilidad(x)
        filas.append({"Proyecto": p, "Participantes": kp["participantes"], "Postulaciones": kp["postulaciones"],
                      "Contratados": kp["contratados"], "Colocación %": kp["colocacion"],
                      "Deserción %": kp["desercion"]})
    st.dataframe(filas, hide_index=True, use_container_width=True)
