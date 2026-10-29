"""
EFE General › Consulta -- migrado de "Consulta" de «Dash General EFE2» (n8n).

Buscador de personas por documento o nombre, con su estado en cada fuente:
seguimiento (programa, estado, resultado), satisfacción (NPS y promedio de sus encuestas),
caracterización (ciudad, edad, actividad) y empleabilidad (contratación, postulaciones).
Tiene datos personales: solo con login (misma lista del Panel de control) y sin descarga.
"""
import streamlit as st

from utils import efe_data as data
from utils.efe_ui import aplicar, filtro, inicio

inicio("EFE · Consulta", "Búsqueda de participantes por documento o nombre")

with st.spinner("Consultando BigQuery..."):
    seg = data.seguimiento(con_nombre=True)
    sat = data.satisfaccion()
    car = data.caracterizacion()
    emp = data.empleabilidad()

c1, c2, c3, c4 = st.columns([1.6, 1, 1.2, 1])
buscar = c1.text_input("Documento o nombre", key="efe_con_buscar", placeholder="Ej. 1019... o parte del nombre")
proyecto = filtro(seg, "Proyecto", "Proyecto", "efe_con_proy", c2)
df = aplicar(seg, "Proyecto", proyecto)
programa = filtro(df, "Programa", "Programa", "efe_con_prog", c3)
df = aplicar(df, "Programa", programa)
estado = filtro(df, "Estado_academico", "Estado académico", "efe_con_est", c4)
df = aplicar(df, "Estado_academico", estado)

if buscar.strip():
    b = buscar.strip().lower()
    exacto = df[df["Documento"].astype(str) == b]
    df = exacto if not exacto.empty else df[df["Documento"].astype(str).str.contains(b, regex=False)
                                            | df["Nombre"].fillna("").str.lower().str.contains(b, regex=False)]

# Resumen por persona y proyecto de las otras fuentes
sat_p = (sat.groupby(["Documento", "Proyecto"])
         .agg(Encuestas=("NPS", "size"), NPS_prom=("NPS", "mean"), Satisfacción=("Promedio_Satisfaccion", "mean"))
         .reset_index())
car_p = car[["Documento", "Proyecto", "Ciudad_residencia", "Edad", "Actividad_principal"]]
emp_p = (emp.sort_values("postulaciones", ascending=False).drop_duplicates(["Documento", "Proyecto"])
         [["Documento", "Proyecto", "Estado_contratacion", "postulaciones", "Empresa"]])

tabla = (df[["Nombre", "Documento", "Proyecto", "Programa", "Estado_academico", "Resultado_academico", "Ciudad"]]
         .merge(sat_p, on=["Documento", "Proyecto"], how="left")
         .merge(car_p, on=["Documento", "Proyecto"], how="left")
         .merge(emp_p, on=["Documento", "Proyecto"], how="left"))
tabla["Ciudad"] = tabla["Ciudad_residencia"].fillna(tabla["Ciudad"])
tabla = tabla.drop(columns="Ciudad_residencia").rename(columns={
    "Estado_academico": "Estado", "Resultado_academico": "Resultado", "NPS_prom": "NPS (prom.)",
    "Estado_contratacion": "Contratación", "postulaciones": "Postulaciones", "Actividad_principal": "Actividad"})

st.caption(f"{tabla['Documento'].nunique():,} personas · {len(tabla):,} registros (persona × programa)".replace(",", "."))
if not buscar.strip() and len(tabla) > 500:
    st.info("Escribe un documento o nombre para buscar; mientras tanto se muestran los primeros 500 registros.")
st.dataframe(tabla.head(500), hide_index=True, use_container_width=True,
             column_config={"NPS (prom.)": st.column_config.NumberColumn(format="%.1f"),
                            "Satisfacción": st.column_config.NumberColumn(format="%.2f"),
                            "Edad": st.column_config.NumberColumn(format="%d")})

if buscar.strip() and tabla["Documento"].nunique() == 1:
    doc = tabla["Documento"].iloc[0]
    st.subheader(f"Ficha · {tabla['Nombre'].iloc[0] or doc}")
    f1, f2 = st.columns(2)
    with f1:
        st.markdown("**Encuestas de satisfacción**")
        st.dataframe(sat[sat["Documento"] == doc][["Proyecto", "fecha", "NPS", "Promedio_Satisfaccion"]],
                     hide_index=True, use_container_width=True)
    with f2:
        st.markdown("**Caracterización**")
        ficha = car[car["Documento"] == doc].drop(columns=["fecha", "rango_edad"], errors="ignore")
        st.dataframe(ficha.T.astype(str), use_container_width=True)  # texto: la tabla traspuesta mezcla tipos
