"""
IQ / Análisis dinámico -- reemplaza a las páginas Overview + Histórico
(sept-2026, a pedido de Christian: necesitaba comparar por Mes / Trimestre /
Semestre / Año, ver aumentos y descensos año contra año, y filtrar por Rol /
Grado / Región para tomar decisiones de facturación -- las 2 páginas viejas
solo mostraban el mes más reciente y una serie mensual sin filtros
combinables).

Qué hace cada sección (de arriba a abajo):
1. Controles: granularidad (Mes/Trimestre/Semestre/Año), filtros de
   Alianza/Rol/Grado/Región, y período puntual a analizar.
2. KPI de cabecera: usuarios activos y horas totales del período elegido,
   con las 2 comparaciones lado a lado -- vs período inmediatamente
   anterior y vs mismo período del año anterior.
3. Comparativa trimestral año contra año (Q1..Q4, una barra por año) --
   siempre visible, sin importar la granularidad elegida en (1).
4. Distribución mensual por año (cuartiles estadísticos: caja = P25-P75,
   línea = mediana) -- para ver dispersión y crecimiento entre años.
5. Tendencia histórica en la granularidad elegida, con los huecos de
   exportación sombreados (igual criterio que la vieja página Histórico).
6. Tabla de períodos con variación %, descargable.

Ver utils/iq_usage_hours.py para la lógica de datos -- incluye la
limitación conocida de sobre-conteo al combinar varios valores de una
misma dimensión (ej. 2 grados a la vez) con filtros activos.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from utils.iq_usage_hours import (
    COLOR_PROGRAMA,
    GRANOS,
    agregar_comparaciones,
    alianzas_disponibles,
    hay_filtro_dimensional,
    huecos_en_rango,
    load_cobertura_huecos,
    rango_fechas_periodo,
    serie,
    serie_total,
    usage_hours_actualizado_al,
    valores_dimension,
)
from utils.ui import badge, dark, inject_css, kpi_row

inject_css()

st.markdown(badge("IQ · Análisis dinámico", "#29B6F6"), unsafe_allow_html=True)
st.title("Análisis dinámico")
st.caption(f"Datos de uso al {usage_hours_actualizado_al()} (fuente: `active_usage_hours`, BigQuery).")

alianzas_todas = alianzas_disponibles()
if not alianzas_todas:
    st.error(
        "No encontré los agregados en `data/iq/usage_hours/`. Esta página depende de "
        "`totales_*.csv` / `detalle_*.csv` -- revisa que estén en el repo."
    )
    st.stop()

# ============================================================================
# 1) Controles
# ============================================================================
c1, c2 = st.columns([1, 3])
with c1:
    grano_label = st.selectbox("Granularidad", list(GRANOS.keys()), index=0)
grano = GRANOS[grano_label]
with c2:
    alianzas_sel = st.multiselect("Alianza", alianzas_todas, default=alianzas_todas)

fc1, fc2, fc3 = st.columns(3)
with fc1:
    rol_sel = st.multiselect("Rol", valores_dimension("Rol"), default=[], help="Vacío = todos los roles.")
with fc2:
    grado_sel = st.multiselect("Grado", valores_dimension("Grado"), default=[], help="Vacío = todos los grados.")
with fc3:
    region_sel = st.multiselect(
        "Región", valores_dimension("region_norm"), default=[], help="Vacío = todas las regiones."
    )

if hay_filtro_dimensional(rol_sel, grado_sel, region_sel):
    st.caption(
        "ℹ️ Con filtros de Rol/Grado/Región activos, los números se recalculan sumando las "
        "combinaciones que calzan con lo elegido. Si seleccionas **más de un valor dentro de la "
        "misma categoría** (ej. 2 grados a la vez), una persona que aparece en ambos valores en el "
        "mismo período se cuenta una vez por cada uno -- es una limitación de trabajar con "
        "agregados estáticos y no con la data cruda en vivo (ver Cobertura). Sin estos filtros, "
        "los números de abajo son exactos."
    )

if not alianzas_sel:
    st.info("Selecciona al menos una Alianza para continuar.")
    st.stop()

serie_df = serie(grano, alianzas_sel, rol_sel, grado_sel, region_sel)
if serie_df.empty:
    st.warning("No hay datos para esta combinación de filtros.")
    st.stop()

total_df = serie_total(grano, alianzas_sel, rol_sel, grado_sel, region_sel)
total_df = agregar_comparaciones(total_df, grano)

periodos_labels = total_df["_label"].tolist()
periodo_sel_label = st.selectbox("Período a analizar (para el KPI de cabecera)", periodos_labels, index=len(periodos_labels) - 1)
fila = total_df[total_df["_label"] == periodo_sel_label].iloc[0]

# -- aviso si el período elegido cae dentro de un hueco confirmado ----------
sub_col = {"mensual": "Mes", "trimestral": "Trimestre", "semestral": "Semestre", "anual": None}[grano]
sub_val = fila[sub_col] if sub_col else None
ini, fin = rango_fechas_periodo(grano, fila["Anio"], sub_val)
huecos_periodo = huecos_en_rango(ini, fin)
if not huecos_periodo.empty:
    for _, h in huecos_periodo.iterrows():
        st.warning(
            f"⚠️ Este período incluye un hueco confirmado de exportación "
            f"({h['desde'].date()} a {h['hasta'].date()}) -- los números de abajo están por "
            f"debajo de la actividad real. Ver página **Cobertura**."
        )

# ============================================================================
# 2) KPI de cabecera -- 2 comparaciones lado a lado
# ============================================================================
def _var(v) -> str:
    if pd.isna(v):
        return "sin dato para comparar"
    signo = "+" if v >= 0 else ""
    return f"{signo}{v:.1f}%"


if grano == "anual":
    ayuda_usuarios = f"{_var(fila['var_usuarios_ant_pct'])} vs año anterior"
    ayuda_horas = f"{_var(fila['var_horas_ant_pct'])} vs año anterior"
else:
    ayuda_usuarios = (
        f"{_var(fila['var_usuarios_ant_pct'])} vs período anterior · "
        f"{_var(fila['var_usuarios_anio_pct'])} vs mismo período año anterior"
    )
    ayuda_horas = (
        f"{_var(fila['var_horas_ant_pct'])} vs período anterior · "
        f"{_var(fila['var_horas_anio_pct'])} vs mismo período año anterior"
    )

st.markdown(f"##### {periodo_sel_label} -- los 2 factores de facturación")
kpi_row(
    [
        ("Usuarios activos", f"{int(fila['usuarios_activos']):,}".replace(",", "."), "#29B6F6", ayuda_usuarios),
        ("Horas totales de logueo", f"{fila['horas_totales']:,.0f} h".replace(",", "."), "#FD531E", ayuda_horas),
    ]
)

# ============================================================================
# 3) Comparativa trimestral año contra año (fija, no depende de (1))
# ============================================================================
st.markdown("##### Comparativa trimestral, año contra año")
tri = serie_total("trimestral", alianzas_sel, rol_sel, grado_sel, region_sel)
tri["Trimestre_label"] = "T" + tri["Trimestre"].str[1]
tri["Año"] = tri["Anio"].astype(str)

tc1, tc2 = st.columns(2)
with tc1:
    fig = px.bar(
        tri.sort_values(["Trimestre_label", "Anio"]),
        x="Trimestre_label", y="usuarios_activos", color="Año", barmode="group",
        title="Usuarios activos por trimestre",
    )
    fig.update_layout(xaxis_title="")
    st.plotly_chart(dark(fig), width="stretch")
with tc2:
    fig = px.bar(
        tri.sort_values(["Trimestre_label", "Anio"]),
        x="Trimestre_label", y="horas_totales", color="Año", barmode="group",
        title="Horas totales por trimestre",
    )
    fig.update_layout(xaxis_title="")
    st.plotly_chart(dark(fig), width="stretch")

# ============================================================================
# 4) Distribución mensual por año (cuartiles estadísticos)
# ============================================================================
st.markdown("##### Distribución mensual por año")
st.caption(
    "Cada caja resume los 12 (o menos) valores mensuales de ese año: la caja va del percentil 25 "
    "al 75, la línea del medio es la mediana, y los puntos son meses atípicos -- útil para ver si "
    "un año creció/se dispersó más que otro, más allá del total acumulado."
)
mensual_tot = serie_total("mensual", alianzas_sel, rol_sel, grado_sel, region_sel)
mensual_tot["Año"] = mensual_tot["Anio"].astype(str)

qc1, qc2 = st.columns(2)
with qc1:
    fig = px.box(mensual_tot, x="Año", y="usuarios_activos", points="all", title="Usuarios activos (mensual) por año")
    st.plotly_chart(dark(fig), width="stretch")
with qc2:
    fig = px.box(mensual_tot, x="Año", y="horas_totales", points="all", title="Horas totales (mensual) por año")
    st.plotly_chart(dark(fig), width="stretch")

# ============================================================================
# 5) Tendencia histórica en la granularidad elegida
# ============================================================================
st.markdown(f"##### Tendencia histórica ({grano_label.lower()})")

huecos = load_cobertura_huecos()
if not huecos.empty:
    st.info(
        "🔲 Las franjas grises marcan huecos confirmados de exportación (ningún archivo fuente "
        "cubre esas fechas) -- no son caídas reales de actividad. Detalle en la página **Cobertura**."
    )


def _fecha_inicio(row):
    sv = row[sub_col] if sub_col else None
    ini, _ = rango_fechas_periodo(grano, row["Anio"], sv)
    return ini


serie_df["fecha_inicio"] = serie_df.apply(_fecha_inicio, axis=1)


def _agregar_huecos(fig):
    for _, h in huecos.iterrows():
        fig.add_vrect(x0=h["desde"], x1=h["hasta"], fillcolor="gray", opacity=0.3, line_width=0)
    return fig


fig = px.line(
    serie_df.sort_values("fecha_inicio"), x="fecha_inicio", y="usuarios_activos", color="Programa",
    color_discrete_map=COLOR_PROGRAMA, markers=True, title="Usuarios activos",
)
fig.update_layout(xaxis_title="")
st.plotly_chart(dark(_agregar_huecos(fig)), width="stretch")

fig = px.line(
    serie_df.sort_values("fecha_inicio"), x="fecha_inicio", y="horas_totales", color="Programa",
    color_discrete_map=COLOR_PROGRAMA, markers=True, title="Horas totales de logueo",
)
fig.update_layout(xaxis_title="")
st.plotly_chart(dark(_agregar_huecos(fig)), width="stretch")

# ============================================================================
# 6) Tabla de períodos con variación %
# ============================================================================
with st.expander("Ver tabla de períodos con variación", expanded=False):
    tabla = total_df.sort_values("_orden", ascending=False)[
        [
            "_label", "usuarios_activos", "var_usuarios_ant_pct", "var_usuarios_anio_pct",
            "horas_totales", "var_horas_ant_pct", "var_horas_anio_pct",
        ]
    ].rename(
        columns={
            "_label": "Período",
            "usuarios_activos": "Usuarios activos",
            "var_usuarios_ant_pct": "Δ% vs anterior",
            "var_usuarios_anio_pct": "Δ% vs año anterior",
            "horas_totales": "Horas totales",
            "var_horas_ant_pct": "Δ% vs anterior ",
            "var_horas_anio_pct": "Δ% vs año anterior ",
        }
    )
    st.dataframe(
        tabla.style.format(
            {
                "Usuarios activos": "{:,.0f}",
                "Δ% vs anterior": "{:+.1f}%",
                "Δ% vs año anterior": "{:+.1f}%",
                "Horas totales": "{:,.0f}",
                "Δ% vs anterior ": "{:+.1f}%",
                "Δ% vs año anterior ": "{:+.1f}%",
            },
            na_rep="--",
        ),
        hide_index=True, width="stretch",
    )
    csv = tabla.to_csv(index=False).encode("utf-8")
    st.download_button("Descargar CSV (períodos y variación)", csv, f"iq_analisis_{grano}.csv", "text/csv")
