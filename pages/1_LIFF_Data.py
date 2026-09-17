"""
Pestaña LIFF Data.

Fuente de datos: Google Sheets (pestaña "LIF_Data_Export"), llenada por un
workflow de n8n que consulta BigQuery directamente. Ver utils/sheets.py y
queries/liff_data.py para el detalle de arquitectura.

Las reglas de negocio (qué cuenta como "retenido", cómo se clasifica un
módulo en Cursado/En Curso/Próximo, qué es "Aprobación") NO viven aquí --
están en utils/liff_metrics.py, con la justificación de cada una. Si un
número no cuadra contra el dashboard viejo de Looker, revisa ese archivo
primero.

Este archivo es SOLO presentación: tarjetas de KPI con acento de color,
paneles con borde para las gráficas, y secciones con encabezado propio.
Si algo se ve descuadrado en tu resolución de pantalla, es este archivo
el que hay que tocar -- los cálculos están aislados en liff_metrics.py.

Clic-para-filtrar: las 5 gráficas de categoría simple (Estado Académico,
Estado del Módulo, Aprobación, y las 2 "por Programa") tienen on_select --
un clic en una barra/porción actualiza el selectbox correspondiente, igual
que si lo eligieras del dropdown. Ver utils/ui.click_to_filter() para el
mecanismo. Las gráficas de la sección Comparativo NO son clickeables a
propósito -- comparan 2 poblaciones a la vez, no son "una categoría por
segmento".
"""
import plotly.express as px
import streamlit as st

from utils.liff_metrics import (
    ORDEN_APROBACION,
    ORDEN_ESTADO_MODULO,
    aprobacion_counts,
    comparativo_kpis,
    enrich,
    estado_academico_counts,
    estado_modulo_counts,
    estudiantes_por_programa,
    kpis_overview,
    modulos_por_estado_pct_comparativo,
    nota_promedio_por_programa,
)
from utils.sheets import get_liff_data
from utils.ui import (
    AMARILLO,
    AZUL,
    CHART_HEIGHT,
    GRIS,
    NARANJA,
    ROJO,
    VERDE,
    badge as _badge,
    click_to_filter,
    dark as _dark,
    inject_css,
    kpi_row as _kpi_row,
)

inject_css()

with st.spinner("Leyendo datos desde Google Sheets..."):
    df_raw = get_liff_data()

if df_raw.empty:
    st.warning(
        "LIF_Data_Export no tiene filas todavía. Verifica que el workflow "
        "de n8n ya corrió al menos una vez."
    )
    st.stop()

df = enrich(df_raw)
df_ext_full = df[df["_POBLACION"] == "extranjero"]
df_nac_full = df[df["_POBLACION"] == "nacional"]

# ---------------------------------------------------------------------------
# Overview -- extranjeros
# ---------------------------------------------------------------------------
col_title, col_badge = st.columns([5, 1], vertical_alignment="center")
col_title.title("LIFF Data")
col_badge.markdown(
    _badge(f"{len(df_ext_full)} REGISTROS DE MÓDULOS"), unsafe_allow_html=True
)
st.caption("Estudiantes extranjeros (PPT / Pasaporte / CE / Documento extranjero)")

TODOS_PROGRAMAS = "Todos los Programas"
TODOS_ESTADOS = "Todos los Estados"
TODOS_ESTADO_MODULO = "Todos"
TODOS_APROBACION = "Todos"

with st.container(border=True):
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    programas = [TODOS_PROGRAMAS] + sorted(
        df_ext_full["PROGRAMA"].dropna().unique().tolist()
    )
    estados = [TODOS_ESTADOS] + sorted(
        df_ext_full["ESTADO"].dropna().unique().tolist()
    )
    programa_sel = col_f1.selectbox("Filtrar por programa", programas, key="liff_programa_sel")
    estado_sel = col_f2.selectbox(
        "Filtrar por estado académico", estados, key="liff_estado_sel"
    )
    estado_modulo_sel = col_f3.selectbox(
        "Filtrar por estado del módulo",
        [TODOS_ESTADO_MODULO] + ORDEN_ESTADO_MODULO,
        key="liff_estado_modulo_sel",
    )
    aprobacion_sel = col_f4.selectbox(
        "Filtrar por aprobación",
        [TODOS_APROBACION] + ORDEN_APROBACION,
        key="liff_aprobacion_sel",
    )

df_ext = df_ext_full.copy()
if programa_sel != TODOS_PROGRAMAS:
    df_ext = df_ext[df_ext["PROGRAMA"] == programa_sel]
if estado_sel != TODOS_ESTADOS:
    df_ext = df_ext[df_ext["ESTADO"] == estado_sel]
if estado_modulo_sel != TODOS_ESTADO_MODULO:
    df_ext = df_ext[df_ext["_ESTADO_MODULO"] == estado_modulo_sel]
if aprobacion_sel != TODOS_APROBACION:
    df_ext = df_ext[df_ext["_APROBACION"] == aprobacion_sel]

st.write("")

if df_ext.empty:
    st.info("No hay registros para esta combinación de filtros.")
else:
    kpis = kpis_overview(df_ext)

    st.subheader("Indicadores generales")
    _kpi_row(
        [
            ("Estudiantes", str(kpis["estudiantes"]), NARANJA, ""),
            ("Programas", str(kpis["programas"]), NARANJA, ""),
            (
                "% Retención",
                f"{kpis['pct_retencion']:.1f}%",
                VERDE,
                "Activos / Total extranjeros",
            ),
            (
                "% Aprobación",
                f"{kpis['pct_aprobacion']:.1f}%",
                NARANJA,
                "Sobre módulos con nota publicada",
            ),
            ("Nota Promedio", f"{kpis['nota_promedio']:.1f}", NARANJA, ""),
        ]
    )

    st.write("")
    st.subheader("Estado de los módulos")
    _kpi_row(
        [
            ("Módulos Cursados", str(kpis["modulos_cursados"]), AZUL, ""),
            ("Módulos En Curso", str(kpis["modulos_en_curso"]), AMARILLO, ""),
            ("Módulos Próximos", str(kpis["modulos_proximos"]), VERDE, ""),
        ]
    )

    st.write("")
    st.subheader("Distribución")
    g1, g2, g3 = st.columns(3)

    with g1, st.container(border=True):
        df_estado_acad = estado_academico_counts(df_ext)
        fig_estado_acad = px.pie(
            df_estado_acad,
            names="estado",
            values="cantidad",
            hole=0.55,
            title="Estado Académico",
            color_discrete_sequence=[NARANJA, AZUL, GRIS],
            custom_data=["estado"],
        )
        fig_estado_acad.update_traces(textinfo="value+percent")
        st.plotly_chart(
            _dark(fig_estado_acad),
            width="stretch",
            key="liff_chart_estado_acad",
            on_select=click_to_filter("liff_chart_estado_acad", "liff_estado_sel"),
            selection_mode="points",
        )

    with g2, st.container(border=True):
        df_estado_mod = estado_modulo_counts(df_ext)
        fig_estado_mod = px.bar(
            df_estado_mod,
            x="categoria",
            y="cantidad",
            title="Módulos: Cursados / En Curso / Próximos",
            color="categoria",
            color_discrete_map={"Cursado": AZUL, "En Curso": AMARILLO, "Próximo": VERDE},
            text="cantidad",
            custom_data=["categoria"],
        )
        fig_estado_mod.update_layout(showlegend=False, xaxis_title=None, yaxis_title=None)
        st.plotly_chart(
            _dark(fig_estado_mod),
            width="stretch",
            key="liff_chart_estado_mod",
            on_select=click_to_filter("liff_chart_estado_mod", "liff_estado_modulo_sel"),
            selection_mode="points",
        )

    with g3, st.container(border=True):
        df_aprob = aprobacion_counts(df_ext)
        fig_aprob = px.pie(
            df_aprob,
            names="categoria",
            values="cantidad",
            hole=0.55,
            title="Aprobación de Módulos",
            color="categoria",
            color_discrete_map={
                "Aprobado": VERDE,
                "No Aprobado": ROJO,
                "Pendiente de Nota": GRIS,
            },
            custom_data=["categoria"],
        )
        fig_aprob.update_traces(textinfo="value+percent")
        st.plotly_chart(
            _dark(fig_aprob),
            width="stretch",
            key="liff_chart_aprob",
            on_select=click_to_filter("liff_chart_aprob", "liff_aprobacion_sel"),
            selection_mode="points",
        )

    st.write("")
    st.subheader("Por programa")
    g4, g5 = st.columns(2)

    with g4, st.container(border=True):
        df_est_prog = estudiantes_por_programa(df_ext)
        fig_est_prog = px.bar(
            df_est_prog,
            x="estudiantes",
            y="PROGRAMA",
            orientation="h",
            title="Estudiantes por Programa",
            text="estudiantes",
            color_discrete_sequence=[NARANJA],
            custom_data=["PROGRAMA"],
        )
        fig_est_prog.update_layout(yaxis_title=None, xaxis_title=None)
        st.plotly_chart(
            _dark(fig_est_prog),
            width="stretch",
            key="liff_chart_est_prog",
            on_select=click_to_filter("liff_chart_est_prog", "liff_programa_sel"),
            selection_mode="points",
        )

    with g5, st.container(border=True):
        df_nota_prog = nota_promedio_por_programa(df_ext)
        fig_nota_prog = px.bar(
            df_nota_prog,
            x="nota_promedio",
            y="PROGRAMA",
            orientation="h",
            title="Nota Promedio por Programa",
            text=df_nota_prog["nota_promedio"].round(2) if not df_nota_prog.empty else None,
            color_discrete_sequence=[AZUL],
            custom_data=["PROGRAMA"],
        )
        fig_nota_prog.update_layout(yaxis_title=None, xaxis_title=None)
        st.plotly_chart(
            _dark(fig_nota_prog),
            width="stretch",
            key="liff_chart_nota_prog",
            on_select=click_to_filter("liff_chart_nota_prog", "liff_programa_sel"),
            selection_mode="points",
        )

# ---------------------------------------------------------------------------
# Comparativo: extranjeros vs nacionales -- siempre sobre el total de cada
# población, SIN los filtros de programa/estado del overview (los filtros
# solo acotan la vista de extranjeros de arriba).
# ---------------------------------------------------------------------------
st.divider()

comp = comparativo_kpis(df_ext_full, df_nac_full)
ext, nac = comp["extranjero"], comp["nacional"]

col_ctitle, col_cbadge = st.columns([5, 1], vertical_alignment="center")
col_ctitle.subheader("Comparativo: Extranjeros vs Nacionales")
badge_comparativo = f"{ext['modulos']:,} VS {nac['modulos']:,} REGISTROS"
col_cbadge.markdown(_badge(badge_comparativo), unsafe_allow_html=True)

st.write("")
_kpi_row(
    [
        (
            "Estudiantes",
            f"{ext['estudiantes']} vs {nac['estudiantes']}",
            NARANJA,
            "Extranjeros vs Nacionales",
        ),
        (
            "% Aprobación",
            f"{ext['pct_aprobacion']:.1f}% vs {nac['pct_aprobacion']:.1f}%",
            NARANJA,
            "",
        ),
        (
            "Nota Promedio",
            f"{ext['nota_promedio']:.1f} vs {nac['nota_promedio']:.1f}",
            NARANJA,
            "",
        ),
    ]
)

st.write("")
with st.container(border=True):
    df_comp = modulos_por_estado_pct_comparativo(df_ext_full, df_nac_full)
    fig_comp = px.bar(
        df_comp,
        x="categoria",
        y="porcentaje",
        color="poblacion",
        barmode="group",
        text=df_comp["porcentaje"].round(1).astype(str) + "%",
        title="Módulos por Estado (% del total de cada población)",
        color_discrete_map={"Extranjeros": NARANJA, "Nacionales": AZUL},
        category_orders={"categoria": ["Cursado", "En Curso", "Próximo"]},
    )
    fig_comp.update_layout(yaxis_title="% del total", xaxis_title=None)
    st.plotly_chart(_dark(fig_comp, height=CHART_HEIGHT + 60), width="stretch")
