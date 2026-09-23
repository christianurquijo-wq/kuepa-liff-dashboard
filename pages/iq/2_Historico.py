
import pandas as pd
import plotly.express as px
import streamlit as st

from utils.iq_usage_hours import COLOR_PROGRAMA, load_cobertura_huecos, load_mensual_alianza, usage_hours_actualizado_al
from utils.ui import badge, dark, inject_css

inject_css()

st.markdown(badge("IQ · Histórico", "#29B6F6"), unsafe_allow_html=True)
st.title("Histórico")
st.caption(f"Datos de uso al {usage_hours_actualizado_al()} (fuente: `active_usage_hours`, BigQuery).")

df = load_mensual_alianza()
if df.empty:
    st.error("No encontré `data/iq/usage_hours/mensual_alianza.csv`.")
    st.stop()
df["periodo"] = pd.to_datetime(dict(year=df["Anio"], month=df["Mes"], day=1))
huecos = load_cobertura_huecos()

alianzas_disp = sorted(df["Programa"].unique())
alianzas_sel = st.multiselect("Alianza", alianzas_disp, default=alianzas_disp)
rango = st.slider(
    "Rango de meses",
    min_value=df["periodo"].min().to_pydatetime(),
    max_value=df["periodo"].max().to_pydatetime(),
    value=(df["periodo"].min().to_pydatetime(), df["periodo"].max().to_pydatetime()),
    format="MM/YYYY",
)

f = df[df["Programa"].isin(alianzas_sel) & df["periodo"].between(rango[0], rango[1])]

if not huecos.empty:
    st.info(
        "🔲 Las franjas grises en los gráficos marcan huecos confirmados de exportación "
        "(ningún archivo fuente cubre esas fechas) — no son caídas reales de actividad. "
        "Detalle en la página **Cobertura**."
    )


def _agregar_huecos(fig):
    for _, h in huecos.iterrows():
        fig.add_vrect(
            x0=h["desde"], x1=h["hasta"],
            fillcolor="gray", opacity=0.3, line_width=0,
        )
    return fig


st.markdown("##### Usuarios activos por mes")
fig = px.line(
    f.sort_values("periodo"), x="periodo", y="usuarios_activos", color="Programa",
    color_discrete_map=COLOR_PROGRAMA, markers=True,
)
st.plotly_chart(dark(_agregar_huecos(fig)), width="stretch")

st.markdown("##### Horas totales de logueo por mes")
fig = px.line(
    f.sort_values("periodo"), x="periodo", y="horas_totales", color="Programa",
    color_discrete_map=COLOR_PROGRAMA, markers=True,
)
st.plotly_chart(dark(_agregar_huecos(fig)), width="stretch")

with st.expander("Ver tabla"):
    pivote_usuarios = f.pivot_table(
        index="periodo", columns="Programa", values="usuarios_activos", aggfunc="sum"
    ).sort_index(ascending=False)
    st.markdown("**Usuarios activos**")
    st.dataframe(pivote_usuarios, width="stretch")
    pivote_horas = f.pivot_table(
        index="periodo", columns="Programa", values="horas_totales", aggfunc="sum"
    ).sort_index(ascending=False).round(1)
    st.markdown("**Horas totales**")
    st.dataframe(pivote_horas, width="stretch")

    csv = f.sort_values("periodo").to_csv(index=False).encode("utf-8")
    st.download_button("Descargar CSV (selección actual)", csv, "iq_historico.csv", "text/csv")
