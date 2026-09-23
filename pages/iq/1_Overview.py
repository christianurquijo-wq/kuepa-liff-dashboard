
import pandas as pd
import plotly.express as px
import streamlit as st

from utils.iq_usage_hours import (
    COLOR_PROGRAMA,
    load_cobertura_huecos,
    load_mensual_alianza,
    usage_hours_actualizado_al,
)
from utils.ui import AMARILLO, GRIS, badge, dark, inject_css, kpi_row

inject_css()

st.markdown(badge("IQ · Overview", "#29B6F6"), unsafe_allow_html=True)
st.title("Overview")
st.caption(f"Datos de uso al {usage_hours_actualizado_al()} (fuente: `active_usage_hours`, BigQuery).")

df = load_mensual_alianza()
if df.empty:
    st.error(
        "No encontré `data/iq/usage_hours/mensual_alianza.csv`. Esta página depende de los "
        "resúmenes agregados de `active_usage_hours` -- revisa que el archivo esté en el repo."
    )
    st.stop()

huecos = load_cobertura_huecos()

# -- selector de mes ---------------------------------------------------------
df["periodo"] = pd.to_datetime(dict(year=df["Anio"], month=df["Mes"], day=1))
periodos = sorted(df["periodo"].unique())
default_idx = len(periodos) - 1
_MESES_ES = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto",
             "septiembre","octubre","noviembre","diciembre"]


def _mes_es(p) -> str:
    ts = pd.Timestamp(p)
    return f"{_MESES_ES[ts.month - 1].capitalize()} {ts.year}"


periodo_sel = st.selectbox(
    "Mes",
    periodos,
    index=default_idx,
    format_func=_mes_es,
)
periodo_sel = pd.Timestamp(periodo_sel)

# aviso si el mes elegido cae dentro de un hueco confirmado de exportación
if not huecos.empty:
    for _, h in huecos.iterrows():
        desde, hasta = pd.Timestamp(h["desde"]), pd.Timestamp(h["hasta"])
        if desde.replace(day=1) <= periodo_sel <= hasta:
            st.warning(
                f"⚠️ Este mes incluye un hueco confirmado de exportación "
                f"({h['desde']} a {h['hasta']}, {h['dias']} días sin datos en ninguna fuente) — "
                f"los números de abajo están por debajo de la actividad real. Ver página **Cobertura**."
            )

# mes anterior para variación
idx_actual = periodos.index(pd.Timestamp(periodo_sel))
periodo_ant = periodos[idx_actual - 1] if idx_actual > 0 else None

mes_actual = df[df["periodo"] == periodo_sel]
mes_ant = df[df["periodo"] == periodo_ant] if periodo_ant is not None else pd.DataFrame()


def _var_pct(actual: float, anterior: float) -> str:
    if not anterior:
        return ""
    var = (actual - anterior) / anterior * 100
    signo = "+" if var >= 0 else ""
    return f"{signo}{var:.1f}% vs mes anterior"


usuarios_total = int(mes_actual["usuarios_activos"].sum())
horas_total = float(mes_actual["horas_totales"].sum())
usuarios_ant = int(mes_ant["usuarios_activos"].sum()) if not mes_ant.empty else 0
horas_ant = float(mes_ant["horas_totales"].sum()) if not mes_ant.empty else 0

st.markdown("##### Los 2 factores de facturación mensual")
kpi_row(
    [
        ("Usuarios activos (mes)", f"{usuarios_total:,}".replace(",", "."), "#29B6F6", _var_pct(usuarios_total, usuarios_ant)),
        ("Horas totales de logueo (mes)", f"{horas_total:,.0f} h".replace(",", "."), "#FD531E", _var_pct(horas_total, horas_ant)),
    ]
)

st.markdown("##### Desglose por Alianza")
tabla = mes_actual[["Programa", "usuarios_activos", "horas_totales", "registros"]].rename(
    columns={"usuarios_activos": "Usuarios activos", "horas_totales": "Horas totales", "registros": "Registros"}
).sort_values("Usuarios activos", ascending=False)
st.dataframe(tabla, hide_index=True, width="stretch")

c1, c2 = st.columns(2)
with c1:
    fig = px.bar(
        mes_actual.sort_values("usuarios_activos", ascending=False),
        x="Programa", y="usuarios_activos", color="Programa",
        color_discrete_map=COLOR_PROGRAMA, title="Usuarios activos por Alianza",
    )
    fig.update_layout(showlegend=False)
    st.plotly_chart(dark(fig), width="stretch")
with c2:
    fig = px.bar(
        mes_actual.sort_values("horas_totales", ascending=False),
        x="Programa", y="horas_totales", color="Programa",
        color_discrete_map=COLOR_PROGRAMA, title="Horas totales por Alianza",
    )
    fig.update_layout(showlegend=False)
    st.plotly_chart(dark(fig), width="stretch")

with st.expander("Ver tabla completa (todos los meses)"):
    st.dataframe(
        df[["periodo", "Programa", "usuarios_activos", "horas_totales", "registros"]]
        .sort_values("periodo", ascending=False),
        hide_index=True, width="stretch",
    )
