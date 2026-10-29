"""
EFE General › Overview -- migrado de la pestaña "Overview" de «Dash General EFE2» (n8n).

Fuente: vista EFE_2026.Unificado_Seguimiento (estado actual, una fila por persona x programa).
Definiciones de cada KPI: utils/efe_metrics.py (docstring). Proyectos: Colsubsidio 2026,
Colsubsidio 2.0 2026, Suba es Oportunidad, Ecolombia 2.0 y Jóvenes a la E.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import efe_data as data
from utils import efe_metrics as m
from utils.efe_ui import TODOS, aplicar, barras, conteo, dona, filtro, inicio
from utils.ui import AZUL, GRIS, NARANJA, ROJO, VERDE, dark, kpi_row

inicio("EFE · Overview", "Estado académico actual de todos los proyectos EFE · fuente: Unificado_Seguimiento")

with st.spinner("Consultando BigQuery..."):
    base = data.seguimiento()

if base.empty:
    st.warning("Unificado_Seguimiento no devolvió filas. Revisa la vista en BigQuery o el acceso de la cuenta de servicio.")
    st.stop()

c1, c2, _ = st.columns([1, 1.4, 1])
proyecto = filtro(base, "Proyecto", "Proyecto", "efe_ov_proy", c1)
df = aplicar(base, "Proyecto", proyecto)
programa = filtro(df, "Programa", "Programa", "efe_ov_prog", c2)
df = aplicar(df, "Programa", programa)

k = m.kpis_seguimiento(df)
kpi_row([
    ("Inscritos", m.fmt_num(k["inscritos"]), GRIS, "Personas registradas"),
    ("Impactados", m.fmt_num(k["impactados"]), NARANJA, "Iniciaron formación"),
    ("Activos", m.fmt_num(k["activos"]), AZUL, ""),
    ("Finalizados", m.fmt_num(k["finalizados"]), VERDE, ""),
])
st.write("")
kpi_row([
    ("Retención", m.fmt_pct(k["retencion"]), VERDE, "Activo + Finalizado + Aplazado ÷ impactados"),
    ("Deserción", m.fmt_pct(k["desercion"]), ROJO, "Retiro + Expulsado ÷ impactados"),
    ("Aprobación", m.fmt_pct(k["aprobacion"]), NARANJA, f"Sobre {m.fmt_num(k['calificados'])} con nota · "
                                                       f"{m.fmt_num(k['pendiente_nota'])} pendientes de nota"),
    ("Matrícula no exitosa", m.fmt_num(k["no_exitosa"]), GRIS, "Personas que no completaron matrícula"),
])

st.divider()
col_a, col_b = st.columns(2)
with col_a:
    # Embudo académico (personas)
    etapas = ["Inscritos", "Impactados", "Activos + Finalizados", "Finalizados"]
    valores = [k["inscritos"], k["impactados"], k["activos"] + k["finalizados"], k["finalizados"]]
    fig = go.Figure(go.Funnel(y=etapas, x=valores, textinfo="value+percent initial",
                              marker={"color": [GRIS, NARANJA, AZUL, VERDE]}))
    fig.update_layout(title="Embudo académico")
    st.plotly_chart(dark(fig, 340), use_container_width=True)
with col_b:
    dona(m.genero(df.drop_duplicates("Documento")["Sexo"]).value_counts(), "Género (según seguimiento)",
         colores=m.COLORES_GENERO)

col_c, col_d = st.columns(2)
with col_c:
    barras(conteo(df[df["impactado"]], "Programa"), "Programa", "Personas", "Impactados por programa", horizontal=True)
with col_d:
    barras(conteo(df, "Estado_academico"), "Estado_academico", "Personas", "Personas por estado académico",
           horizontal=True)

if proyecto == TODOS:
    st.subheader("Comparativo por proyecto")
    filas = []
    for p, x in df.groupby("Proyecto"):
        kp = m.kpis_seguimiento(x)
        filas.append({"Proyecto": p, "Inscritos": kp["inscritos"], "Impactados": kp["impactados"],
                      "Activos": kp["activos"], "Finalizados": kp["finalizados"],
                      "Retención %": kp["retencion"], "Deserción %": kp["desercion"],
                      "Aprobación %": kp["aprobacion"], "Matrícula no exitosa": kp["no_exitosa"]})
    tabla = pd.DataFrame(filas)
    st.dataframe(tabla, hide_index=True, use_container_width=True,
                 column_config={c: st.column_config.NumberColumn(format="%.1f%%")
                                for c in ("Retención %", "Deserción %", "Aprobación %")})

with st.expander("¿Cómo se calcula cada indicador?"):
    st.markdown(
        "- **Impactados**: personas en estado Activo, Finalizado, Retiro, Aplazado o Expulsado.\n"
        "- **Retención / Deserción**: sobre inscripciones impactadas (persona × programa).\n"
        "- **Aprobación**: Aprobado ÷ (Aprobado + Reprobado); *Pendiente publicar nota* no cuenta.\n"
        "- Datos con caché de 10 minutos. Para ver la evolución en el tiempo, abre **Tendencias**."
    )
