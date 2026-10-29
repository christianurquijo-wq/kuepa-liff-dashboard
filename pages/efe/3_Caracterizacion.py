"""
EFE General › Caracterización -- migrado de la pestaña "Caracterización" de «Dash General EFE2».

Fuente: vista EFE_2026.Unificado_Caracterizacion (encuesta socioeconómica; si una persona la
respondió varias veces en el mismo proyecto, se toma la más reciente).
Los datos se muestran TAL CUAL vienen (decisión de Christian): Colsubsidio 2.0 trae valores
fijos por diseño (edad 23/34/44/54, actividad "Estudiar", ingresos "Hasta 1 SMMLV") y Suba
reporta el estrato como "Pendiente".
"""
import streamlit as st

from utils import efe_data as data
from utils import efe_metrics as m
from utils.efe_ui import aplicar, barras, conteo, dona, filtro, inicio
from utils.ui import AZUL, GRIS, NARANJA, ROJO, VERDE, kpi_row

inicio("EFE · Caracterización", "Perfil socioeconómico de los participantes · fuente: Unificado_Caracterizacion")

with st.spinner("Consultando BigQuery..."):
    base = data.caracterizacion()
if base.empty:
    st.warning("Unificado_Caracterizacion no devolvió filas.")
    st.stop()

c1, _ = st.columns([1, 2])
proyecto = filtro(base, "Proyecto", "Proyecto", "efe_car_proy", c1)
df = aplicar(base, "Proyecto", proyecto)

k = m.kpis_caracterizacion(df)
kpi_row([
    ("Caracterizados", m.fmt_num(k["caracterizados"]), GRIS, "Personas con encuesta"),
    ("% Nini", m.fmt_pct(k["nini"]), ROJO, "Ni estudia ni trabaja"),
    ("% Mujeres", m.fmt_pct(k["mujeres"]), NARANJA, ""),
    ("% Bajos ingresos", m.fmt_pct(k["bajos_ingresos"]), AZUL, "Hasta 1 SMMLV (con dato)"),
    ("Edad promedio", m.fmt_num(k["edad_promedio"], 1), VERDE, "Años"),
])

st.divider()
col_a, col_b = st.columns(2)
with col_a:
    dona(m.genero(df["Sexo"]).value_counts(), "Distribución por género", colores=m.COLORES_GENERO)
with col_b:
    barras(conteo(df, "rango_edad").astype({"rango_edad": str}), "rango_edad", "Personas",
           "Distribución por rangos de edad", orden=m.ORDEN_EDAD + ["Sin dato"])

col_c, col_d = st.columns(2)
with col_c:
    dona(df["Actividad_principal"].fillna("Sin dato").value_counts(), "Situación laboral / académica")
with col_d:
    barras(conteo(df, "Escolaridad"), "Escolaridad", "Personas", "Nivel de escolaridad", horizontal=True)

col_e, col_f = st.columns(2)
with col_e:
    barras(conteo(df, "Estrato"), "Estrato", "Personas", "Estrato socioeconómico",
           orden=[f"Estrato {i}" for i in range(1, 7)] + ["No aplica", "Pendiente", "Sin dato"])
with col_f:
    dona(df["Ingresos"].fillna("Sin dato").value_counts(), "Nivel de ingresos mensuales")

barras(conteo(df, "Numero_hijos_Personas_cargo"), "Numero_hijos_Personas_cargo", "Personas",
       "Hijos / personas a cargo", orden=["No tengo hijos", "Uno (1)", "Dos (2)", "Tres (3) o más",
                                          "Sin información", "Sin dato"])
