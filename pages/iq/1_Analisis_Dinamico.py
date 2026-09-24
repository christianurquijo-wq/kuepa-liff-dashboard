"""
IQ / Análisis dinámico -- reemplaza a las páginas Overview + Histórico
(sept-2026, a pedido de Christian: necesitaba comparar por Mes / Trimestre /
Semestre / Año, ver aumentos y descensos año contra año, y filtrar por Rol /
Grado / Región para tomar decisiones de facturación -- las 2 páginas viejas
solo mostraban el mes más reciente y una serie mensual sin filtros
combinables).

Qué hace cada sección (de arriba a abajo):
1. Controles: granularidad (Mes/Trimestre/Semestre/Año), filtros de
   Alianza/Rol/Grado/Región, y período puntual a analizar. Con
   granularidad Mes aparece además un deslizable de intervalo (ej. abr-2026
   a jul-2026) que acota TODO lo de abajo excepto (3) y (4), que siempre
   muestran el histórico completo por diseño.
2. KPI de cabecera: usuarios activos y horas totales del período elegido,
   con las 2 comparaciones lado a lado -- vs período inmediatamente
   anterior y vs mismo período del año anterior.
3. Comparativa año contra año -- granularidad (Mes/Trimestre/Semestre/Año)
   y deslizable de intervalo PROPIOS, independientes de (1) -- por diseño
   esta sección es la vista "ancla" de la página y no se mueve sola cuando
   cambias los controles de arriba.
4. Distribución entre años (cuartiles estadísticos: caja = P25-P75,
   línea = mediana) -- granularidad y deslizable PROPIOS, igual que (3).
   Eje X = sub-período (Mes/Trimestre/Semestre); cada caja resume los años
   disponibles para ese sub-período -- para ver dispersión y crecimiento
   entre años, mes a mes (o trimestre/semestre a semestre).
5. Tendencia histórica en la granularidad elegida, con los huecos de
   exportación sombreados (igual criterio que la vieja página Histórico).
6. Tabla de períodos con variación %, descargable.

Ver utils/iq_usage_hours.py para la lógica de datos -- incluye la
limitación conocida de sobre-conteo al combinar varios valores de una
misma dimensión (ej. 2 grados a la vez) con filtros activos.
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from utils.iq_usage_hours import (
    COLOR_PROGRAMA_DISPLAY,
    GRANOS,
    MESES_ES,
    PERIOD_COLS,
    agregar_comparaciones,
    alianzas_disponibles,
    etiqueta_programa,
    hay_filtro_dimensional,
    huecos_en_rango,
    load_cobertura_huecos,
    rango_fechas_periodo,
    serie,
    serie_facturado,
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
    alianzas_sel = st.multiselect(
        "Alianza", alianzas_todas, default=alianzas_todas, format_func=etiqueta_programa
    )

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
# Comparaciones (vs período anterior / vs mismo período año anterior) se
# calculan ANTES de acotar por el intervalo de abajo -- así el primer mes
# visible sigue mostrando su variación aunque el mes anterior a él haya
# quedado fuera del rango elegido.
total_df = agregar_comparaciones(total_df, grano)

# ============================================================================
# 1.4) Intervalo de tiempo (solo con granularidad Mes)
# ============================================================================
if grano == "mensual":
    meses_ordenados = total_df.sort_values("_orden")["_label"].tolist()
    if len(meses_ordenados) > 1:
        mes_desde, mes_hasta = st.select_slider(
            "Intervalo de tiempo",
            options=meses_ordenados,
            value=(meses_ordenados[0], meses_ordenados[-1]),
            help=(
                "Acota Real vs. facturado, Tendencia histórica y la tabla de períodos a este "
                "rango de meses. La comparativa trimestral y la distribución mensual por año "
                "(más abajo) siempre muestran el histórico completo, sin importar este control."
            ),
        )
        orden_ini = total_df.loc[total_df["_label"] == mes_desde, "_orden"].iloc[0]
        orden_fin = total_df.loc[total_df["_label"] == mes_hasta, "_orden"].iloc[0]
        total_df = total_df[(total_df["_orden"] >= orden_ini) & (total_df["_orden"] <= orden_fin)]
        serie_df = serie_df[(serie_df["_orden"] >= orden_ini) & (serie_df["_orden"] <= orden_fin)]

# ============================================================================
# 1.5) Real vs. facturado (Excel "Usuarios activos LMS - Proyectos Inicia")
# ============================================================================
st.divider()
st.markdown("##### Real vs. facturado")
st.caption(
    "Compara lo que arroja `active_usage_hours` (en vivo) contra el Excel de facturación de "
    "Christian, que es ESTÁTICO -- se actualiza a mano y por ahora llega hasta agosto 2026."
)

facturado_df = serie_facturado(grano, alianzas_sel)
if facturado_df.empty:
    st.info(
        "No hay datos facturados para esta combinación de Alianza en este período -- el Excel "
        "de facturación no cubre esta selección."
    )
else:
    if hay_filtro_dimensional(rol_sel, grado_sel, region_sel):
        st.caption(
            "ℹ️ El Excel de facturación no tiene desglose por Rol/Grado/Región -- la línea "
            "facturada siempre muestra el total del programa completo, aunque los filtros de "
            "arriba acoten lo real. No son comparables 1 a 1 mientras estos filtros estén activos."
        )

    ver_sel = st.radio(
        "Ver", ["Horas y usuarios", "Solo horas", "Solo usuarios"],
        horizontal=True, key="iqad_ver_comparativo",
    )
    mostrar_horas = ver_sel in ("Horas y usuarios", "Solo horas")
    mostrar_usuarios = ver_sel in ("Horas y usuarios", "Solo usuarios")

    cols_join = PERIOD_COLS[grano]
    comp = total_df[cols_join + ["_orden", "_label", "usuarios_activos", "horas_totales"]].merge(
        facturado_df[cols_join + ["usuarios_facturados", "horas_facturados"]],
        on=cols_join, how="left",
    ).sort_values("_orden")

    fig_comp = make_subplots(specs=[[{"secondary_y": True}]])
    if mostrar_horas:
        fig_comp.add_trace(
            go.Scatter(x=comp["_label"], y=comp["horas_totales"], name="Horas reales",
                       mode="lines+markers", line=dict(color="#FD531E")),
            secondary_y=False,
        )
        fig_comp.add_trace(
            go.Scatter(x=comp["_label"], y=comp["horas_facturados"], name="Horas facturadas",
                       mode="lines+markers", line=dict(color="#FD531E", dash="dot")),
            secondary_y=False,
        )
    if mostrar_usuarios:
        fig_comp.add_trace(
            go.Scatter(x=comp["_label"], y=comp["usuarios_activos"], name="Usuarios reales",
                       mode="lines+markers", line=dict(color="#29B6F6")),
            secondary_y=mostrar_horas,
        )
        fig_comp.add_trace(
            go.Scatter(x=comp["_label"], y=comp["usuarios_facturados"], name="Usuarios facturados",
                       mode="lines+markers", line=dict(color="#29B6F6", dash="dot")),
            secondary_y=mostrar_horas,
        )
    if mostrar_horas:
        fig_comp.update_yaxes(title_text="Horas", secondary_y=False)
    if mostrar_usuarios:
        fig_comp.update_yaxes(title_text="Usuarios", secondary_y=mostrar_horas)
    fig_comp.update_layout(xaxis_title=None)
    st.plotly_chart(dark(fig_comp), width="stretch", key="iqad_chart_comparativo")

    with st.expander("Ver tabla real vs. facturado"):
        tabla_comp = comp[
            ["_label", "usuarios_activos", "usuarios_facturados", "horas_totales", "horas_facturados"]
        ].rename(columns={
            "_label": "Período",
            "usuarios_activos": "Usuarios reales",
            "usuarios_facturados": "Usuarios facturados",
            "horas_totales": "Horas reales",
            "horas_facturados": "Horas facturadas",
        })
        st.dataframe(tabla_comp, width="stretch", hide_index=True)

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
# 3) Comparativa año contra año -- granularidad y deslizable PROPIOS,
#    independientes de la sección 1 (esta sección es la vista "ancla")
# ============================================================================
st.markdown("##### Comparativa año contra año")

c3_1, c3_2 = st.columns([1, 3])
with c3_1:
    grano3_label = st.selectbox(
        "Granularidad", list(GRANOS.keys()), index=1, key="iqad_grano3",
        help="Selector propio de esta sección -- no depende del de Controles, arriba.",
    )
grano3 = GRANOS[grano3_label]

tri = serie_total(grano3, alianzas_sel, rol_sel, grado_sel, region_sel)

if tri.empty:
    st.info("No hay datos para esta combinación de filtros y granularidad.")
else:
    # -- deslizable de intervalo, en las 4 granularidades -----------------
    periodos3 = tri.sort_values("_orden")["_label"].tolist()
    if len(periodos3) > 1:
        with c3_2:
            p3_desde, p3_hasta = st.select_slider(
                "Intervalo",
                options=periodos3,
                value=(periodos3[0], periodos3[-1]),
                key="iqad_slider3",
                help="Acota qué años/períodos entran en esta comparación.",
            )
        orden3_ini = tri.loc[tri["_label"] == p3_desde, "_orden"].iloc[0]
        orden3_fin = tri.loc[tri["_label"] == p3_hasta, "_orden"].iloc[0]
        tri = tri[(tri["_orden"] >= orden3_ini) & (tri["_orden"] <= orden3_fin)]

    tri = tri.copy()
    tri["Año"] = tri["Anio"].astype(str)

    # -- etiqueta de sub-período dentro del año, en orden cronológico -----
    # (en "Año" no hay sub-período -- una sola barra por año, ver más abajo)
    if grano3 == "mensual":
        tri["_sub"] = tri["Mes"].astype(int).apply(lambda m: MESES_ES[m - 1][:3])
        orden_x = [MESES_ES[i][:3] for i in range(12)]
    elif grano3 == "trimestral":
        tri["_sub"] = "T" + tri["Trimestre"].str[1]
        orden_x = ["T1", "T2", "T3", "T4"]
    elif grano3 == "semestral":
        tri["_sub"] = "S" + tri["Semestre"].str[1]
        orden_x = ["S1", "S2"]
    else:
        orden_x = None

    def _grafico_yoy(y_col: str, y_titulo: str, color_solido: str):
        """Un gráfico por debajo del otro (antes iban lado a lado) para
        dejar espacio a estos controles propios y a comparaciones futuras."""
        if grano3 == "anual":
            # Sin sub-período -- una barra por año, sin agrupar ni leyenda.
            fig = px.bar(tri.sort_values("_orden"), x="Año", y=y_col, title=f"{y_titulo} por año")
            fig.update_traces(marker_color=color_solido)
            fig.update_layout(showlegend=False)
        else:
            fig = px.bar(
                tri.sort_values("_orden"), x="_sub", y=y_col, color="Año", barmode="group",
                title=f"{y_titulo} por {grano3_label.lower()}",
            )
            fig.update_xaxes(categoryorder="array", categoryarray=orden_x)
        fig.update_layout(xaxis_title="")
        fig.update_yaxes(title_text=y_titulo)
        return fig

    st.plotly_chart(dark(_grafico_yoy("usuarios_activos", "Usuarios activos", "#29B6F6")), width="stretch")
    st.plotly_chart(dark(_grafico_yoy("horas_totales", "Horas totales", "#FD531E")), width="stretch")

# ============================================================================
# 4) Distribución entre años -- granularidad y deslizable PROPIOS (mismo
#    patrón que la sección 3). oct-2026: se invirtió el eje X (antes era
#    Año con cajas de valores mensuales dentro de ese año; el hover de los
#    puntos atípicos entonces mostraba el Año -- el mismo dato que el eje X
#    -- y nunca decía a qué mes correspondía cada punto). Ahora el eje X es
#    el sub-período (Ene..Dic / T1..T4 / S1..S2) y cada caja resume los
#    AÑOS disponibles para ese sub-período, así el hover de cada punto
#    atípico sí puede mostrar su Año (el dato que faltaba).
# ============================================================================
st.markdown("##### Distribución entre años")
st.caption(
    "Cada caja resume, para un mismo mes/trimestre/semestre, los valores de los distintos años "
    "disponibles: la caja va del percentil 25 al 75, la línea del medio es la mediana, y los "
    "puntos son años atípicos -- pasa el cursor sobre un punto para ver a qué año corresponde."
)

c4_1, c4_2 = st.columns([1, 3])
with c4_1:
    grano4_label = st.selectbox(
        "Granularidad", ["Mes", "Trimestre", "Semestre"], index=0, key="iqad_grano4",
        help=(
            "Selector propio de esta sección -- no depende del de Controles, arriba. No incluye "
            "'Año' porque cada caja necesita varios puntos (años) por sub-período, y en 'Año' solo "
            "habría un valor por año -- no hay nada que distribuir."
        ),
    )
grano4 = GRANOS[grano4_label]

dist_df = serie_total(grano4, alianzas_sel, rol_sel, grado_sel, region_sel)

if dist_df.empty:
    st.info("No hay datos para esta combinación de filtros y granularidad.")
else:
    periodos4 = dist_df.sort_values("_orden")["_label"].tolist()
    if len(periodos4) > 1:
        with c4_2:
            p4_desde, p4_hasta = st.select_slider(
                "Intervalo",
                options=periodos4,
                value=(periodos4[0], periodos4[-1]),
                key="iqad_slider4",
                help="Acota qué años/períodos entran en esta distribución.",
            )
        orden4_ini = dist_df.loc[dist_df["_label"] == p4_desde, "_orden"].iloc[0]
        orden4_fin = dist_df.loc[dist_df["_label"] == p4_hasta, "_orden"].iloc[0]
        dist_df = dist_df[(dist_df["_orden"] >= orden4_ini) & (dist_df["_orden"] <= orden4_fin)]

    dist_df = dist_df.copy()
    dist_df["Año"] = dist_df["Anio"].astype(str)

    if grano4 == "mensual":
        dist_df["_sub"] = dist_df["Mes"].astype(int).apply(lambda m: MESES_ES[m - 1][:3])
        orden_x4 = [MESES_ES[i][:3] for i in range(12)]
    elif grano4 == "trimestral":
        dist_df["_sub"] = "T" + dist_df["Trimestre"].str[1]
        orden_x4 = ["T1", "T2", "T3", "T4"]
    else:  # semestral
        dist_df["_sub"] = "S" + dist_df["Semestre"].str[1]
        orden_x4 = ["S1", "S2"]

    def _grafico_dist(y_col: str, y_titulo: str):
        """Un gráfico por debajo del otro (antes iban lado a lado) --
        mismo criterio que la sección 3, deja más espacio a los controles
        propios y a las etiquetas del eje X."""
        fig = px.box(
            dist_df.sort_values("_orden"), x="_sub", y=y_col, points="all",
            hover_data={"Año": True, "_sub": False},
            title=f"{y_titulo} ({grano4_label.lower()}) -- distribución entre años",
        )
        fig.update_xaxes(categoryorder="array", categoryarray=orden_x4, title="")
        fig.update_yaxes(title_text=y_titulo)
        return fig

    st.plotly_chart(dark(_grafico_dist("usuarios_activos", "Usuarios activos")), width="stretch")
    st.plotly_chart(dark(_grafico_dist("horas_totales", "Horas totales")), width="stretch")

# ============================================================================
# 5) Tendencia histórica en la granularidad elegida
# ============================================================================
st.markdown(f"##### Tendencia histórica ({grano_label.lower()})")

huecos = load_cobertura_huecos()


def _fecha_inicio(row):
    sv = row[sub_col] if sub_col else None
    ini, _ = rango_fechas_periodo(grano, row["Anio"], sv)
    return ini


serie_df["fecha_inicio"] = serie_df.apply(_fecha_inicio, axis=1)
serie_df["Programa"] = serie_df["Programa"].map(etiqueta_programa)  # solo para mostrar -- ver nota en iq_usage_hours.py


def _agregar_huecos(fig):
    for _, h in huecos.iterrows():
        fig.add_vrect(x0=h["desde"], x1=h["hasta"], fillcolor="gray", opacity=0.3, line_width=0)
    return fig


fig = px.line(
    serie_df.sort_values("fecha_inicio"), x="fecha_inicio", y="usuarios_activos", color="Programa",
    color_discrete_map=COLOR_PROGRAMA_DISPLAY, markers=True, title="Usuarios activos",
)
fig.update_layout(xaxis_title="")
st.plotly_chart(dark(_agregar_huecos(fig)), width="stretch")

fig = px.line(
    serie_df.sort_values("fecha_inicio"), x="fecha_inicio", y="horas_totales", color="Programa",
    color_discrete_map=COLOR_PROGRAMA_DISPLAY, markers=True, title="Horas totales de logueo",
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
