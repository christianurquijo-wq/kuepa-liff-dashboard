"""
Pestaña LIFF Data -- Matrícula (CRM) + Académico (SIS), consulta unificada
(sept-2026, reemplaza a la versión anterior solo-académica).

Fuente de datos: Google Sheets, llenada por un workflow de n8n que
consulta BigQuery directamente (mismo patrón que la versión anterior --
ver utils/liff_crm_data.py y queries/liff_data.py). Sin
st.secrets["liff_crm"] configurado, la página cae a datos de
DEMOSTRACIÓN (sintéticos) y lo avisa con un banner.

Grano de la fuente: 1 fila por matriculado/prematriculado + materia
cursada en el SIS (prematriculados y matriculados sin usuario SIS traen 1
sola fila, con los campos académicos en NULL). Por eso el funnel y los
KPIs de matrícula dedupean por persona (INCREMENTAL_LEAD_CODE) -- ver
utils/liff_metrics.py::_por_persona() -- y el bloque académico se separa
aparte con academico_de() antes de reutilizar toda la lógica de
Cursado/Aprobación/Retención que ya existía (utils/liff_metrics.py,
reglas 1-4, sin cambios).

Filtros globales (Programa/Asesor/Campaña/Tipo, arriba de todo) aplican a
las pestañas 1, 2 y 3 -- la 3 (Comparativo) ANTES los ignoraba a propósito
(comparaba siempre el total), pero desde que pasó a ser la vista central
de la página (oct-2026, a pedido de Christian) también los respeta, para
poder comparar Extranjero/Nacional DENTRO de un programa o asesor
puntual. Botón de descarga a Excel (arriba de las pestañas) exporta
exactamente esa misma selección filtrada.

4 secciones:
  1. Funnel y calidad de datos -- prematriculado -> matriculado por
     asesor/campaña/programa, tendencia mensual, y el panel de
     ALERTA_SIN_USUARIO_SIS.
  2. Académico -- igual que la página vieja (Cursado/En Curso/Próximo,
     Aprobación, Nota promedio), sobre las filas con match académico
     real, con filtros adicionales propios (Estado Académico/Estado del
     Módulo) en un expander.
  3. Comparativo Extranjero/Nacional -- pestaña CENTRAL (oct-2026): todos
     los indicadores académicos lado a lado (estudiantes, retención,
     aprobación, nota), tendencia mensual por población,
     y cruces de % aprobación por Programa/Asesor. La población sale del
     SIS y solo existe para quien tiene match académico -- el funnel
     completo (conversión, sin usuario SIS) no se puede repartir por
     población y queda en la pestaña 1, con un caption acá que lo explica
     en vez de inventar un reparto.
  4. Caracterización y satisfacción -- esquema real confirmado (sept-2026,
     dos pestañas del spreadsheet "LIF Data"):
       - "Satisfacción" (gid=0): puntajes TUTORES/CONTENIDO/PLATAFORMA/
         SERVICIO, NPS y cruce contra % de aprobación académica por
         documento.
       - "Caracterización" (gid=250569807): encuesta socioeconómica larga
         (~65 preguntas) -- se muestran 6 dimensiones clave (estrato,
         estado civil, nivel escolar, empleabilidad, ingreso, género)
         detectadas por substring (no por nombre exacto -- el texto de
         cada pregunta es largo y podría variar levemente) más cruce
         contra desempeño académico.
     Ninguna hoja tenía respuestas reales al momento de programar esto,
     así que todo se parsea de forma defensiva: si un valor no convierte
     a número o no se detecta una columna esperada, se avisa en vez de
     graficar/cruzar algo inventado. El perfilador genérico por columna
     queda como respaldo para lo que no está cubierto arriba.

oct-2026: corte de técnicos FIJO (ver utils/liff_metrics.py, regla 5 y
FECHA_CORTE_TECNICOS) -- toda la página excluye registros anteriores al
1 de agosto de 2026. Bloque CRM/funnel: por _FECHA_CORTE_REF (híbrido --
FECHA_INICIO_GRUPO cuando existe, si no CREATED_AT_DATE), aplicado una
sola vez sobre `df` justo después de enrich_crm(), así que alcanza
automáticamente a las 4 pestañas. Bloque académico: por _FECHA_INICIO
(FECHA_INICIO_GRUPO), aplicado en cada punto donde se deriva el subset
académico (academico_de() + enrich()) -- es un criterio MÁS estricto que
el del funnel (ahí nunca hay fallback a CREATED_AT_DATE porque ya hay
match real), no una alternativa, y por eso se aplican los dos en cadena.
Sin toggle en la página (a pedido explícito de Christian); si en algún
momento hace falta ver el histórico completo, hay que pedir un cambio de
código.

oct-2026 (2): "Monto recaudado" se quitó de la vista en las 4 pestañas
(sigue calculándose en utils/liff_metrics.py, solo no se muestra). Se
extendió la diferenciación Extranjero/Nacional -- antes solo en la
pestaña Comparativo -- a Académico (mismo _POBLACION del bloque
académico, sin pérdida) y a Satisfacción/Caracterización (cruzando por
documento contra el académico; quien no cruza queda sin clasificar y no
entra en esas comparativas). Ver utils/liff_metrics.py, reglas 6 y 7.
"""
import io

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.liff_crm_data import (
    CARACTERIZACION_DIMENSIONES,
    SAT_COLUMNAS_SCORE,
    detectar_columna_documento,
    detectar_columna_grupo,
    detectar_columna_nps,
    load_caracterizacion,
    load_liff_crm,
    load_satisfaccion,
)
from utils.liff_metrics import (
    FECHA_CORTE_TECNICOS,
    ORDEN_APROBACION,
    ORDEN_ESTADO_MODULO,
    academico_de,
    academico_resumen_por_dimension_poblacion,
    academico_resumen_por_persona,
    alerta_sin_usuario_tabla,
    aprobacion_pct_poblacion,
    comparativo_kpis,
    enrich,
    enrich_crm,
    estado_academico_pct_poblacion,
    filtrar_corte_tecnicos_academico,
    filtrar_corte_tecnicos_funnel,
    funnel_kpis,
    funnel_por_categoria,
    kpis_overview,
    modulos_por_estado_pct_comparativo,
    nota_promedio_por_programa_poblacion,
    tendencia_mensual_funnel,
    tendencia_mensual_poblacion,
)
from utils.ui import (
    AMARILLO,
    AZUL,
    CHART_HEIGHT,
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

with st.spinner("Leyendo Matrícula + Académico..."):
    df_raw, es_demo = load_liff_crm()

col_title, col_badge = st.columns([5, 1], vertical_alignment="center")
col_title.title("LIFF Data")
col_badge.markdown(_badge("MATRÍCULA + ACADÉMICO"), unsafe_allow_html=True)
st.caption("Consulta unificada CRM (matriculados/prematriculados) + estado académico detallado (SIS).")
st.caption(
    f"📅 Corte fijo: solo se analizan registros desde el {FECHA_CORTE_TECNICOS.strftime('%d/%m/%Y')} "
    "(ingreso a programas técnicos) en adelante -- ver utils/liff_metrics.py, regla 5."
)

if es_demo:
    st.warning(
        "⚠️ Mostrando datos de DEMOSTRACIÓN (sintéticos) -- no hay "
        "`st.secrets['liff_crm']` configurado todavía. Ver README para el paso a paso."
    )

if df_raw.empty:
    st.info("No hay filas todavía. Verifica que el workflow de n8n ya corrió al menos una vez.")
    st.stop()

df = enrich_crm(df_raw)
df = filtrar_corte_tecnicos_funnel(df)
if df.empty:
    st.info(f"No hay registros desde el {FECHA_CORTE_TECNICOS.strftime('%d/%m/%Y')} todavía.")
    st.stop()

# ---------------------------------------------------------------------------
# Filtros globales -- aplican a las 4 secciones
# ---------------------------------------------------------------------------
TODOS = "Todos"
with st.container(border=True):
    fc1, fc2, fc3, fc4 = st.columns(4)
    programas = [TODOS] + sorted(df["PROGRAMA_CRM"].dropna().unique().tolist())
    asesores = [TODOS] + sorted(df["SALES_ADVISOR_FULL_NAME"].dropna().unique().tolist())
    campanas = [TODOS] + sorted(df["CAMPAIGN_DATA_NAME"].dropna().unique().tolist())
    tipos = [TODOS, "MATRICULADO", "PREMATRICULADO"]

    programa_sel = fc1.selectbox("Programa (CRM)", programas, key="liff_programa_sel")
    asesor_sel = fc2.selectbox("Asesor", asesores, key="liff_asesor_sel")
    campana_sel = fc3.selectbox("Campaña", campanas, key="liff_campana_sel")
    tipo_sel = fc4.selectbox("Tipo de matrícula", tipos, key="liff_tipo_sel")

f = df.copy()
if programa_sel != TODOS:
    f = f[f["PROGRAMA_CRM"] == programa_sel]
if asesor_sel != TODOS:
    f = f[f["SALES_ADVISOR_FULL_NAME"] == asesor_sel]
if campana_sel != TODOS:
    f = f[f["CAMPAIGN_DATA_NAME"] == campana_sel]
if tipo_sel != TODOS:
    f = f[f["TIPO_MATRICULA"] == tipo_sel]

if f.empty:
    st.info("No hay registros para esta combinación de filtros.")
    st.stop()

# ---------------------------------------------------------------------------
# KPI de cabecera -- funnel + calidad de datos
# ---------------------------------------------------------------------------
kf = funnel_kpis(f)
st.write("")
_kpi_row(
    [
        ("Matriculados", f"{kf['matriculados']:,}".replace(",", "."), VERDE, ""),
        ("Prematriculados", f"{kf['prematriculados']:,}".replace(",", "."), AMARILLO, ""),
        ("% Conversión", f"{kf['pct_conversion']:.1f}%", NARANJA, "Matriculados / Total"),
        (
            "Sin usuario SIS",
            f"{kf['alerta_n']} ({kf['alerta_pct']:.1f}%)",
            ROJO if kf["alerta_n"] else VERDE,
            "Matriculados sin match -- ver pestaña Calidad de datos",
        ),
    ]
)

col_exp1, col_exp2 = st.columns([5, 1])
with col_exp2:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        f.to_excel(writer, sheet_name="Matricula_Academico", index=False)
    st.download_button(
        "⬇️ Excel (filtros aplicados)",
        buf.getvalue(),
        "liff_data_filtrado.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

tab_funnel, tab_academico, tab_comparativo, tab_satisfaccion = st.tabs(
    ["Funnel y calidad de datos", "Académico", "Comparativo Extranjero/Nacional", "Caracterización y satisfacción"]
)

# ---------------------------------------------------------------------------
# TAB 1 -- Funnel y calidad de datos
# ---------------------------------------------------------------------------
with tab_funnel:
    st.subheader("Prematriculado → Matriculado, por dimensión")
    g1, g2 = st.columns(2)
    with g1, st.container(border=True):
        fa = funnel_por_categoria(f, "SALES_ADVISOR_FULL_NAME")
        fig = px.bar(
            fa, x="SALES_ADVISOR_FULL_NAME", y="cantidad", color="TIPO_MATRICULA", barmode="group",
            title="Por asesor", color_discrete_map={"MATRICULADO": VERDE, "PREMATRICULADO": AMARILLO},
        )
        fig.update_layout(xaxis_title=None, yaxis_title=None)
        st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_1")
    with g2, st.container(border=True):
        fc = funnel_por_categoria(f, "CAMPAIGN_DATA_NAME")
        fig = px.bar(
            fc, x="CAMPAIGN_DATA_NAME", y="cantidad", color="TIPO_MATRICULA", barmode="group",
            title="Por campaña", color_discrete_map={"MATRICULADO": VERDE, "PREMATRICULADO": AMARILLO},
        )
        fig.update_layout(xaxis_title=None, yaxis_title=None)
        st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_2")

    with st.container(border=True):
        fp = funnel_por_categoria(f, "PROGRAMA_CRM")
        fig = px.bar(
            fp, x="PROGRAMA_CRM", y="cantidad", color="TIPO_MATRICULA", barmode="group",
            title="Por programa (CRM)", color_discrete_map={"MATRICULADO": VERDE, "PREMATRICULADO": AMARILLO},
        )
        fig.update_layout(xaxis_title=None, yaxis_title=None)
        st.plotly_chart(_dark(fig, height=CHART_HEIGHT + 40), width="stretch", key="liff_chart_3")

    st.divider()
    st.subheader("Tendencia mensual")
    tend_funnel = tendencia_mensual_funnel(f)
    if tend_funnel.empty:
        st.caption("No hay fechas de creación suficientes para armar la tendencia.")
    else:
        with st.container(border=True):
            fig = px.bar(
                tend_funnel, x="_MES", y="cantidad", color="TIPO_MATRICULA", barmode="stack",
                title="Matriculados y Prematriculados por mes (según fecha de creación del lead)",
                color_discrete_map={"MATRICULADO": VERDE, "PREMATRICULADO": AMARILLO},
            )
            fig.update_layout(xaxis_title=None, yaxis_title=None)
            st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_tendencia_funnel")

    st.divider()
    st.subheader("Calidad de datos: matriculados sin usuario SIS")
    st.caption(
        "Matriculados (no prematriculados) sin usuario asociado en el SIS -- posible cédula mal "
        "digitada en CRM o en el SIS, o el usuario todavía no se ha creado allá. No se basa en "
        "\"sin materias\": un matriculado con usuario SIS pero grupo iniciado antes del "
        "2026-08-01 también sale sin datos académicos, y ESO es esperado por el filtro de fecha, "
        "no es una alerta."
    )
    tabla_alerta = alerta_sin_usuario_tabla(f)
    if tabla_alerta.empty:
        st.success("No hay matriculados sin usuario SIS en la selección actual.")
    else:
        st.dataframe(tabla_alerta, hide_index=True, width="stretch")
        csv = tabla_alerta.to_csv(index=False).encode("utf-8")
        st.download_button("Descargar CSV (alerta sin usuario SIS)", csv, "liff_alerta_sin_usuario_sis.csv", "text/csv")

# ---------------------------------------------------------------------------
# TAB 2 -- Académico (misma lógica que la página vieja, sobre el subset
# con match académico real)
# ---------------------------------------------------------------------------
with tab_academico:
    aca_raw = academico_de(f)
    if aca_raw.empty:
        st.info(
            "Nadie en la selección actual tiene datos académicos (o son todos prematriculados / "
            "matriculados sin usuario SIS)."
        )
    else:
        aca = filtrar_corte_tecnicos_academico(enrich(aca_raw))

    if not aca_raw.empty and aca.empty:
        st.info(
            f"Nadie en la selección actual tiene un grupo iniciado desde el "
            f"{FECHA_CORTE_TECNICOS.strftime('%d/%m/%Y')} (corte fijo de la página)."
        )
    elif not aca_raw.empty:

        with st.expander("Filtros adicionales (Académico)", expanded=False):
            fa1, fa2 = st.columns(2)
            opciones_estado = sorted(aca["ESTADO"].dropna().unique().tolist())
            estado_aca_sel = fa1.multiselect("Estado Académico", opciones_estado, key="liff_aca_estado_sel")
            estado_mod_sel = fa2.multiselect("Estado del Módulo", ORDEN_ESTADO_MODULO, key="liff_aca_modulo_sel")
        if estado_aca_sel:
            aca = aca[aca["ESTADO"].isin(estado_aca_sel)]
        if estado_mod_sel:
            aca = aca[aca["_ESTADO_MODULO"].isin(estado_mod_sel)]

        if aca.empty:
            st.info("No hay registros académicos para esta combinación de filtros adicionales.")
        else:
            # _POBLACION ya viene en `aca` (mismo bloque académico que usa
            # Comparativo) y solo toma "extranjero"/"nacional" -- por eso
            # df_ext + df_nac = aca, sin nadie sin clasificar acá (a
            # diferencia de Satisfacción/Caracterización más abajo).
            df_ext = aca[aca["_POBLACION"] == "extranjero"]
            df_nac = aca[aca["_POBLACION"] == "nacional"]
            kpis_ext = kpis_overview(df_ext)
            kpis_nac = kpis_overview(df_nac)

            st.subheader("Indicadores generales -- Extranjeros vs Nacionales")
            _kpi_row(
                [
                    ("Estudiantes", f"{kpis_ext['estudiantes']} vs {kpis_nac['estudiantes']}", NARANJA, "Extranjeros vs Nacionales"),
                    ("Programas", f"{kpis_ext['programas']} vs {kpis_nac['programas']}", NARANJA, ""),
                    ("% Retención", f"{kpis_ext['pct_retencion']:.1f}% vs {kpis_nac['pct_retencion']:.1f}%", VERDE, "Activos / Total con match académico"),
                    ("% Aprobación", f"{kpis_ext['pct_aprobacion']:.1f}% vs {kpis_nac['pct_aprobacion']:.1f}%", NARANJA, "Sobre módulos con nota publicada"),
                    ("Nota Promedio", f"{kpis_ext['nota_promedio']:.1f} vs {kpis_nac['nota_promedio']:.1f}", NARANJA, ""),
                ]
            )

            st.write("")
            st.subheader("Estado de los módulos -- Extranjeros vs Nacionales")
            _kpi_row(
                [
                    ("Módulos Cursados", f"{kpis_ext['modulos_cursados']} vs {kpis_nac['modulos_cursados']}", AZUL, ""),
                    ("Módulos En Curso", f"{kpis_ext['modulos_en_curso']} vs {kpis_nac['modulos_en_curso']}", AMARILLO, ""),
                    ("Módulos Próximos", f"{kpis_ext['modulos_proximos']} vs {kpis_nac['modulos_proximos']}", VERDE, ""),
                ]
            )

            st.write("")
            st.subheader("Distribución -- Extranjeros vs Nacionales")
            st.caption("Cada barra es el % del total DE ESA población (no del total combinado).")
            g1, g2, g3 = st.columns(3)
            with g1, st.container(border=True):
                df_ea = estado_academico_pct_poblacion(df_ext, df_nac)
                fig = px.bar(
                    df_ea, x="estado", y="porcentaje", color="poblacion", barmode="group",
                    title="Estado Académico (%)",
                    color_discrete_map={"Extranjeros": NARANJA, "Nacionales": AZUL},
                    text=df_ea["porcentaje"].round(1).astype(str) + "%",
                )
                fig.update_layout(xaxis_title=None, yaxis_title="% del total", legend_title=None)
                st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_4")

            with g2, st.container(border=True):
                df_em = modulos_por_estado_pct_comparativo(df_ext, df_nac)
                fig = px.bar(
                    df_em, x="categoria", y="porcentaje", color="poblacion", barmode="group",
                    title="Módulos: Cursados / En Curso / Próximos (%)",
                    color_discrete_map={"Extranjeros": NARANJA, "Nacionales": AZUL},
                    category_orders={"categoria": ORDEN_ESTADO_MODULO},
                    text=df_em["porcentaje"].round(1).astype(str) + "%",
                )
                fig.update_layout(xaxis_title=None, yaxis_title="% del total", legend_title=None)
                st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_5")

            with g3, st.container(border=True):
                df_ap = aprobacion_pct_poblacion(df_ext, df_nac)
                fig = px.bar(
                    df_ap, x="categoria", y="porcentaje", color="poblacion", barmode="group",
                    title="Aprobación de Módulos (%)",
                    color_discrete_map={"Extranjeros": NARANJA, "Nacionales": AZUL},
                    category_orders={"categoria": ORDEN_APROBACION},
                    text=df_ap["porcentaje"].round(1).astype(str) + "%",
                )
                fig.update_layout(xaxis_title=None, yaxis_title="% del total", legend_title=None)
                st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_6")

            st.write("")
            st.subheader("Por programa -- Extranjeros vs Nacionales")
            g4, g5 = st.columns(2)
            with g4, st.container(border=True):
                df_ep = academico_resumen_por_dimension_poblacion(df_ext, df_nac, "PROGRAMA")
                fig = px.bar(
                    df_ep, x="estudiantes", y="PROGRAMA", color="poblacion", orientation="h", barmode="group",
                    title="Estudiantes por Programa",
                    color_discrete_map={"Extranjeros": NARANJA, "Nacionales": AZUL},
                )
                fig.update_layout(yaxis_title=None, xaxis_title=None, legend_title=None)
                st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_7")
            with g5, st.container(border=True):
                df_np = nota_promedio_por_programa_poblacion(df_ext, df_nac)
                fig = px.bar(
                    df_np, x="nota_promedio", y="PROGRAMA", color="poblacion", orientation="h", barmode="group",
                    title="Nota Promedio por Programa",
                    color_discrete_map={"Extranjeros": NARANJA, "Nacionales": AZUL},
                )
                fig.update_layout(yaxis_title=None, xaxis_title=None, legend_title=None)
                st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_8")

# ---------------------------------------------------------------------------
# TAB 3 -- Comparativo Extranjero/Nacional -- pestaña central de la página:
# TODOS los indicadores (académico, tendencia, cruces) lado a lado, sobre
# la MISMA selección de filtros de arriba (Programa/Asesor/Campaña/Tipo) --
# antes esta pestaña ignoraba esos filtros a propósito, ahora sí los
# respeta para poder comparar poblaciones DENTRO de un programa/asesor
# puntual, no solo en el total.
#
# La población (Extranjero/Nacional) sale del SIS (DOCTYPE) y solo existe
# para quien tiene match académico real -- por eso el funnel completo
# (matriculados/prematriculados/conversión/alerta sin usuario SIS) NO se
# puede repartir por población y se deja en la pestaña Funnel; acá se
# avisa con un caption en vez de inventar un reparto.
# ---------------------------------------------------------------------------
with tab_comparativo:
    aca_full = academico_de(f)
    if not aca_full.empty:
        aca_full = filtrar_corte_tecnicos_academico(enrich(aca_full))
    if aca_full.empty:
        st.info(
            f"No hay datos académicos para comparar en la selección actual (con grupo iniciado "
            f"desde el {FECHA_CORTE_TECNICOS.strftime('%d/%m/%Y')})."
        )
    else:
        df_ext_full = aca_full[aca_full["_POBLACION"] == "extranjero"]
        df_nac_full = aca_full[aca_full["_POBLACION"] == "nacional"]

        comp = comparativo_kpis(df_ext_full, df_nac_full)
        ext, nac = comp["extranjero"], comp["nacional"]

        col_ct, col_cb = st.columns([5, 1], vertical_alignment="center")
        col_ct.subheader("Extranjeros vs Nacionales -- todos los indicadores")
        col_cb.markdown(_badge(f"{ext['estudiantes']:,} VS {nac['estudiantes']:,} ESTUDIANTES"), unsafe_allow_html=True)
        st.caption(
            "Sobre la selección actual de filtros (Programa/Asesor/Campaña/Tipo). La población sale "
            "del SIS y solo existe para quien tiene match académico -- los "
            f"{kf['alerta_n']} matriculados sin usuario SIS de la selección (pestaña Funnel) no "
            "tienen población asignada todavía y por eso no entran en esta comparación."
        )

        st.write("")
        _kpi_row(
            [
                ("Estudiantes", f"{ext['estudiantes']} vs {nac['estudiantes']}", NARANJA, "Extranjeros vs Nacionales"),
                ("% Retención", f"{ext['pct_retencion']:.1f}% vs {nac['pct_retencion']:.1f}%", VERDE, ""),
                ("% Aprobación", f"{ext['pct_aprobacion']:.1f}% vs {nac['pct_aprobacion']:.1f}%", NARANJA, "Sobre módulos con nota publicada"),
                ("Nota Promedio", f"{ext['nota_promedio']:.1f} vs {nac['nota_promedio']:.1f}", NARANJA, ""),
            ]
        )

        st.write("")
        g1, g2 = st.columns(2)
        with g1, st.container(border=True):
            df_comp = modulos_por_estado_pct_comparativo(df_ext_full, df_nac_full)
            fig = px.bar(
                df_comp, x="categoria", y="porcentaje", color="poblacion", barmode="group",
                text=df_comp["porcentaje"].round(1).astype(str) + "%",
                title="Módulos por Estado (% del total de cada población)",
                color_discrete_map={"Extranjeros": NARANJA, "Nacionales": AZUL},
                category_orders={"categoria": ORDEN_ESTADO_MODULO},
            )
            fig.update_layout(yaxis_title="% del total", xaxis_title=None)
            st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_9")

        with g2, st.container(border=True):
            tend_pob = tendencia_mensual_poblacion(df_ext_full, df_nac_full)
            if tend_pob.empty:
                st.caption("No hay fechas de inicio de grupo suficientes para armar la tendencia.")
            else:
                fig = px.line(
                    tend_pob, x="_MES", y="estudiantes", color="poblacion", markers=True,
                    title="Estudiantes por mes de inicio de grupo",
                    color_discrete_map={"Extranjeros": NARANJA, "Nacionales": AZUL},
                )
                fig.update_layout(xaxis_title=None, yaxis_title=None)
                st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_tendencia_poblacion")

        st.write("")
        st.subheader("Cruces por dimensión")
        dim_sel = st.radio(
            "Cruzar % de aprobación por", ["Programa", "Asesor"], horizontal=True, key="liff_comp_dim_sel",
        )
        columna_cruce = "PROGRAMA" if dim_sel == "Programa" else "SALES_ADVISOR_FULL_NAME"
        df_cruce = academico_resumen_por_dimension_poblacion(df_ext_full, df_nac_full, columna_cruce)
        if df_cruce.empty:
            st.caption("No hay suficientes datos para este cruce en la selección actual.")
        else:
            with st.container(border=True):
                fig = px.bar(
                    df_cruce, x=columna_cruce, y="pct_aprobacion", color="poblacion", barmode="group",
                    title=f"% Aprobación por {dim_sel}, Extranjeros vs Nacionales",
                    color_discrete_map={"Extranjeros": NARANJA, "Nacionales": AZUL},
                )
                fig.update_layout(xaxis_title=None, yaxis_title="% Aprobación")
                st.plotly_chart(_dark(fig, height=CHART_HEIGHT + 60), width="stretch", key="liff_chart_cruce_dim")

# ---------------------------------------------------------------------------
# TAB 4 -- Caracterización y satisfacción -- PENDIENTE de esquema real
# ---------------------------------------------------------------------------
with tab_satisfaccion:
    df_sat, estado_sat = load_satisfaccion()

    if estado_sat == "no_configurado":
        st.info(
            "⏳ Todavía no está conectada la hoja de Satisfacción (pestaña \"Satisfacción\" del "
            "spreadsheet \"LIF Data\").\n\n"
            "**Paso a paso para activarla (lo haces tú, no yo):**\n\n"
            "1. Confirma que esa hoja esté compartida como **Viewer** con "
            "`stc3-editor@sustained-edge-465417-m3.iam.gserviceaccount.com` "
            "(el mismo Service Account que ya usa el resto del proyecto).\n"
            "2. Agrega en `.streamlit/secrets.toml`:\n"
            "```toml\n[satisfaccion]\nsheet_id = \"1eAhgO2RClNg2ULSwYRAF1aXff-PcaBzXYlXr5SrWRTQ\"\n"
            "gid = \"0\"\n```\n"
            "3. Recarga la página."
        )
    elif estado_sat == "error":
        st.error(
            "No pude leer la hoja de Satisfacción/Caracterización -- revisa que el `sheet_id`/`gid` "
            "en secrets.toml sean correctos y que esté compartida con el Service Account."
        )
    elif df_sat.empty:
        st.info("La hoja está conectada pero no tiene filas todavía (0 respuestas por ahora).")
    else:
        st.subheader("Satisfacción")
        col_doc = detectar_columna_documento(df_sat)
        col_nps = detectar_columna_nps(df_sat)
        col_grupo = detectar_columna_grupo(df_sat)
        tiene_scores = all(c in df_sat.columns for c in SAT_COLUMNAS_SCORE)

        # Cruce de población (Extranjero/Nacional) por documento -- esta
        # hoja de Satisfacción NO trae _POBLACION propia (es una encuesta
        # CRM aparte), así que se etiqueta cruzando contra el bloque
        # académico (mismo corte de técnicos que el resto de la página).
        # Quien no cruza (documento no coincide, o no tiene match
        # académico) queda "Sin clasificar" y se excluye de las
        # comparativas ext/nac de abajo -- no se inventa una población.
        # aca_sat/resumen_sat se calculan una sola vez acá y se reutilizan
        # más abajo para el cruce de correlación.
        aca_sat = academico_de(enrich_crm(df_raw))
        if not aca_sat.empty:
            aca_sat = filtrar_corte_tecnicos_academico(enrich(aca_sat))
        resumen_sat = academico_resumen_por_persona(aca_sat) if not aca_sat.empty else pd.DataFrame()

        df_sat = df_sat.copy()
        df_sat["_POBLACION"] = pd.NA
        if col_doc:
            df_sat["_DOC"] = df_sat[col_doc].astype(str).str.strip()
            if not aca_sat.empty and "_POBLACION" in aca_sat.columns:
                poblacion_doc = (
                    aca_sat[["CONTACT_DATA_DOCUMENT_ID", "_POBLACION"]]
                    .dropna()
                    .drop_duplicates("CONTACT_DATA_DOCUMENT_ID")
                    .rename(columns={"CONTACT_DATA_DOCUMENT_ID": "_DOC", "_POBLACION": "_POBLACION_MATCH"})
                )
                poblacion_doc["_DOC"] = poblacion_doc["_DOC"].astype(str).str.strip()
                df_sat = df_sat.merge(poblacion_doc, on="_DOC", how="left")
                df_sat["_POBLACION"] = df_sat["_POBLACION_MATCH"]
                df_sat = df_sat.drop(columns=["_POBLACION_MATCH"])

        # Puntajes TUTORES/CONTENIDO/PLATAFORMA/SERVICIO: probamos si son
        # numéricos. La hoja no tenía respuestas reales todavía al armar
        # esto, así que no asumimos la escala -- si no convierte, avisamos
        # y no inventamos una gráfica sobre texto.
        scores_num = pd.DataFrame()
        if tiene_scores:
            scores_num = df_sat[SAT_COLUMNAS_SCORE].apply(pd.to_numeric, errors="coerce")

        if tiene_scores and scores_num.notna().any().any():
            st.subheader("Satisfacción por categoría")
            promedios = scores_num.mean().round(2)
            _kpi_row(
                [(cat, f"{promedios[cat]:.2f}" if pd.notna(promedios[cat]) else "s/d", NARANJA, "") for cat in SAT_COLUMNAS_SCORE]
            )

            g1, g2 = st.columns(2)
            with g1, st.container(border=True):
                df_prom = promedios.reset_index()
                df_prom.columns = ["categoria", "promedio"]
                fig = px.bar(
                    df_prom, x="categoria", y="promedio", title="Puntaje promedio por categoría",
                    text=df_prom["promedio"].round(2), color_discrete_sequence=[AZUL],
                )
                fig.update_layout(xaxis_title=None, yaxis_title=None)
                st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_10")

            with g2, st.container(border=True):
                if df_sat["_POBLACION"].notna().any():
                    df_pob_scores = pd.concat([df_sat[["_POBLACION"]], scores_num], axis=1).dropna(subset=["_POBLACION"])
                    df_pob_m = (
                        df_pob_scores.groupby("_POBLACION", observed=True)[SAT_COLUMNAS_SCORE]
                        .mean()
                        .reset_index()
                        .melt(id_vars="_POBLACION", var_name="categoria", value_name="promedio")
                    )
                    df_pob_m["_POBLACION"] = df_pob_m["_POBLACION"].map({"extranjero": "Extranjeros", "nacional": "Nacionales"})
                    fig = px.bar(
                        df_pob_m, x="categoria", y="promedio", color="_POBLACION", barmode="group",
                        title="Puntaje promedio -- Extranjeros vs Nacionales",
                        color_discrete_map={"Extranjeros": NARANJA, "Nacionales": AZUL},
                    )
                    fig.update_layout(xaxis_title=None, yaxis_title=None, legend_title=None)
                    st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_10b")
                elif col_grupo:
                    df_grp = pd.concat([df_sat[[col_grupo]], scores_num], axis=1)
                    df_grp = df_grp.groupby(col_grupo, observed=True)[SAT_COLUMNAS_SCORE].mean().reset_index()
                    df_grp_m = df_grp.melt(id_vars=col_grupo, var_name="categoria", value_name="promedio")
                    fig = px.bar(
                        df_grp_m, x=col_grupo, y="promedio", color="categoria", barmode="group",
                        title="Puntaje promedio por grupo",
                    )
                    fig.update_layout(xaxis_title=None, yaxis_title=None)
                    st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_11")
                else:
                    st.caption(
                        "No hay cruce por población todavía (falta columna de documento, o nadie "
                        "cruzó con Académico), ni columna de grupo detectada para comparar este "
                        "promedio."
                    )
        elif tiene_scores:
            st.info(
                "Las columnas TUTORES/CONTENIDO/PLATAFORMA/SERVICIO están, pero no logré leerlas como "
                "números en las respuestas actuales -- revisa el formato en Sheets (¿vienen como texto?)."
            )

        # NPS
        if col_nps:
            nps_num_full = pd.to_numeric(df_sat[col_nps], errors="coerce")
            nps_num = nps_num_full.dropna()
            if not nps_num.empty:
                promotores = (nps_num >= 9).mean() * 100
                detractores = (nps_num <= 6).mean() * 100
                nps_score = promotores - detractores
                st.write("")
                _kpi_row(
                    [
                        ("NPS", f"{nps_score:.0f}", VERDE if nps_score >= 0 else ROJO, f"{col_nps}"),
                        ("Promotores (9-10)", f"{promotores:.1f}%", VERDE, ""),
                        ("Detractores (0-6)", f"{detractores:.1f}%", ROJO, ""),
                    ]
                )

                if df_sat["_POBLACION"].notna().any():
                    filas_nps = []
                    for cod, etiqueta in (("extranjero", "Extranjeros"), ("nacional", "Nacionales")):
                        sub = nps_num_full[(df_sat["_POBLACION"] == cod) & nps_num_full.notna()]
                        if sub.empty:
                            continue
                        prom_p = (sub >= 9).mean() * 100
                        detr_p = (sub <= 6).mean() * 100
                        filas_nps.append({"poblacion": etiqueta, "NPS": prom_p - detr_p, "Promotores": prom_p, "Detractores": detr_p})
                    if filas_nps:
                        df_nps_pob = pd.DataFrame(filas_nps).melt(id_vars="poblacion", var_name="indicador", value_name="valor")
                        with st.container(border=True):
                            fig = px.bar(
                                df_nps_pob, x="indicador", y="valor", color="poblacion", barmode="group",
                                title="NPS -- Extranjeros vs Nacionales",
                                color_discrete_map={"Extranjeros": NARANJA, "Nacionales": AZUL},
                            )
                            fig.update_layout(xaxis_title=None, yaxis_title=None, legend_title=None)
                            st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_nps_pob")

        st.write("")
        if col_doc:
            st.success(f"Cruzando por documento con la columna **{col_doc}**.")
        else:
            st.warning(
                "No encontré una columna obvia de cédula/documento en esta hoja -- dime cuál es "
                "para poder cruzarla con Matrícula + Académico."
            )

        if col_doc and not resumen_sat.empty:
            resumen_sat = resumen_sat.copy()
            resumen_sat["_DOC"] = resumen_sat["CONTACT_DATA_DOCUMENT_ID"].astype(str).str.strip()
            cruzado = df_sat.merge(resumen_sat, on="_DOC", how="inner")
            if cruzado.empty:
                st.caption("No encontré coincidencias de documento entre esta hoja y Matrícula + Académico todavía.")
            else:
                st.caption(f"{len(cruzado):,} personas cruzadas por documento.".replace(",", "."))
                if tiene_scores and scores_num.notna().any().any():
                    # Se recalculan los puntajes DESDE cruzado (no con
                    # scores_num.loc[cruzado.index] como antes) -- merge()
                    # resetea el índice, así que esas posiciones no
                    # correspondían a las filas correctas (bug latente que
                    # nunca se disparó porque la hoja no tenía datos reales
                    # todavía). Así queda alineado sin importar el índice.
                    scores_cruzado = cruzado[SAT_COLUMNAS_SCORE].apply(pd.to_numeric, errors="coerce")
                    pct_num = pd.to_numeric(cruzado["pct_aprobacion_propio"], errors="coerce")
                    cruzado_scores = pd.concat([pct_num.rename("pct_aprobacion_propio"), scores_cruzado], axis=1)
                    corr = cruzado_scores.corr(numeric_only=True)
                    if "pct_aprobacion_propio" in corr.columns and pct_num.notna().sum() >= 2:
                        corr = corr["pct_aprobacion_propio"].drop("pct_aprobacion_propio")
                    else:
                        corr = pd.Series(dtype=float)
                    if corr.empty:
                        st.caption("No hay suficientes datos numéricos todavía para calcular la correlación.")
                    else:
                        with st.container(border=True):
                            df_corr = corr.reset_index()
                            df_corr.columns = ["categoria", "correlacion"]
                            fig = px.bar(
                                df_corr, x="categoria", y="correlacion",
                                title="Correlación entre satisfacción y % de aprobación académica",
                                color_discrete_sequence=[VERDE],
                            )
                            fig.update_layout(xaxis_title=None, yaxis_title=None, yaxis_range=[-1, 1])
                            st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_12")

        st.divider()
        with st.expander("Perfil genérico por columna (todas las preguntas de la encuesta)"):
            # _DOC/_POBLACION son columnas internas que se agregaron arriba
            # para el cruce por población -- no son preguntas de la
            # encuesta, así que se excluyen de este perfilador genérico y
            # del volcado crudo de abajo.
            df_sat_raw = df_sat.drop(columns=["_DOC", "_POBLACION"], errors="ignore")
            st.markdown(f"**{len(df_sat_raw):,}** filas, **{len(df_sat_raw.columns)}** columnas.".replace(",", "."))
            categoricas = [c for c in df_sat_raw.columns if df_sat_raw[c].nunique(dropna=True) <= 20 and c != col_doc]
            if categoricas:
                col_sel = st.selectbox("Columna a explorar", categoricas, key="liff_sat_col_sel")
                counts = df_sat_raw[col_sel].fillna("(vacío)").value_counts().reset_index()
                counts.columns = [col_sel, "cantidad"]
                fig = px.bar(counts, x=col_sel, y="cantidad", title=f"Distribución de {col_sel}", color_discrete_sequence=[AZUL])
                fig.update_layout(xaxis_title=None, yaxis_title=None)
                st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_13")
            st.dataframe(df_sat_raw, width="stretch")

    # -----------------------------------------------------------------------
    # Caracterización (pestaña separada, gid=250569807) -- misma lógica de
    # estados que Satisfacción arriba.
    # -----------------------------------------------------------------------
    st.divider()
    st.subheader("Caracterización")
    df_car, estado_car = load_caracterizacion()

    if estado_car == "no_configurado":
        st.info(
            "⏳ Todavía no está conectada la hoja de Caracterización (pestaña \"Caracterización\" "
            "del spreadsheet \"LIF Data\").\n\n"
            "**Paso a paso para activarla (lo haces tú, no yo):**\n\n"
            "1. Confirma que esa hoja esté compartida como **Viewer** con "
            "`stc3-editor@sustained-edge-465417-m3.iam.gserviceaccount.com`.\n"
            "2. Agrega en `.streamlit/secrets.toml`:\n"
            "```toml\n[caracterizacion]\nsheet_id = \"1eAhgO2RClNg2ULSwYRAF1aXff-PcaBzXYlXr5SrWRTQ\"\n"
            "gid = \"250569807\"\n```\n"
            "3. Recarga la página."
        )
    elif estado_car == "error":
        st.error(
            "No pude leer la hoja de Caracterización -- revisa que el `sheet_id`/`gid` en "
            "secrets.toml sean correctos y que esté compartida con el Service Account."
        )
    elif df_car.empty:
        st.info("La hoja está conectada pero no tiene filas todavía (0 respuestas por ahora).")
    else:
        col_doc_car = detectar_columna_documento(df_car)

        dims_detectadas = [(etiqueta, fn(df_car)) for etiqueta, fn in CARACTERIZACION_DIMENSIONES]
        dims_detectadas = [(etiqueta, col) for etiqueta, col in dims_detectadas if col]

        # Cruce de población (Extranjero/Nacional) por documento -- mismo
        # criterio que en Satisfacción arriba (esta hoja tampoco trae
        # _POBLACION propia). aca_car/resumen_car se calculan una sola vez
        # acá y se reutilizan para el cruce de % aprobación más abajo.
        aca_car = academico_de(enrich_crm(df_raw))
        if not aca_car.empty:
            aca_car = filtrar_corte_tecnicos_academico(enrich(aca_car))
        resumen_car = academico_resumen_por_persona(aca_car) if not aca_car.empty else pd.DataFrame()

        df_car = df_car.copy()
        df_car["_POBLACION"] = pd.NA
        if col_doc_car:
            df_car["_DOC"] = df_car[col_doc_car].astype(str).str.strip()
            if not aca_car.empty and "_POBLACION" in aca_car.columns:
                poblacion_doc_car = (
                    aca_car[["CONTACT_DATA_DOCUMENT_ID", "_POBLACION"]]
                    .dropna()
                    .drop_duplicates("CONTACT_DATA_DOCUMENT_ID")
                    .rename(columns={"CONTACT_DATA_DOCUMENT_ID": "_DOC", "_POBLACION": "_POBLACION_MATCH"})
                )
                poblacion_doc_car["_DOC"] = poblacion_doc_car["_DOC"].astype(str).str.strip()
                df_car = df_car.merge(poblacion_doc_car, on="_DOC", how="left")
                df_car["_POBLACION"] = df_car["_POBLACION_MATCH"]
                df_car = df_car.drop(columns=["_POBLACION_MATCH"])

        hay_poblacion_car = df_car["_POBLACION"].notna().any()

        if not dims_detectadas:
            st.warning(
                "No pude detectar ninguna de las 6 preguntas clave (estrato, estado civil, nivel "
                "escolar, empleabilidad, ingreso, género) por nombre -- puede que el texto de las "
                "preguntas haya cambiado. Revisa el perfil genérico más abajo."
            )
        else:
            st.caption(
                "Perfil socioeconómico -- distribución de las respuestas, Extranjeros vs Nacionales "
                "(quien no cruzó por documento con Académico queda fuera de este reparto)."
                if hay_poblacion_car
                else "Perfil socioeconómico -- distribución de las respuestas."
            )
            cols_grid = st.columns(3)
            for i, (etiqueta, col) in enumerate(dims_detectadas):
                with cols_grid[i % 3], st.container(border=True):
                    if hay_poblacion_car:
                        d = df_car[[col, "_POBLACION"]].dropna(subset=["_POBLACION"]).copy()
                        d[col] = d[col].fillna("(vacío)").astype(str)
                        top_cats = d[col].value_counts().head(12).index
                        d = d[d[col].isin(top_cats)]
                        counts = d.groupby([col, "_POBLACION"], observed=True).size().reset_index(name="cantidad")
                        counts["_POBLACION"] = counts["_POBLACION"].map({"extranjero": "Extranjeros", "nacional": "Nacionales"})
                        fig = px.bar(
                            counts, x=col, y="cantidad", color="_POBLACION", barmode="group", title=etiqueta,
                            color_discrete_map={"Extranjeros": NARANJA, "Nacionales": AZUL},
                        )
                        fig.update_layout(xaxis_title=None, yaxis_title=None, legend_title=None)
                    else:
                        counts = df_car[col].fillna("(vacío)").astype(str).value_counts().head(12).reset_index()
                        counts.columns = [col, "cantidad"]
                        fig = px.bar(counts, x=col, y="cantidad", title=etiqueta, color_discrete_sequence=[AZUL])
                        fig.update_layout(xaxis_title=None, yaxis_title=None)
                    st.plotly_chart(_dark(fig), width="stretch", key=f"liff_car_dim_{i}")

        st.write("")
        if col_doc_car:
            st.success(f"Cruzando por documento con la columna **{col_doc_car}**.")
        else:
            st.warning(
                "No encontré una columna obvia de cédula/documento en esta hoja -- dime cuál es "
                "para poder cruzarla con Matrícula + Académico."
            )

        if col_doc_car and dims_detectadas and not resumen_car.empty:
            resumen_car = resumen_car.copy()
            resumen_car["_DOC"] = resumen_car["CONTACT_DATA_DOCUMENT_ID"].astype(str).str.strip()
            cruzado_car = df_car.merge(resumen_car, on="_DOC", how="inner")
            if cruzado_car.empty:
                st.caption("No encontré coincidencias de documento entre Caracterización y Matrícula + Académico todavía.")
            else:
                st.caption(f"{len(cruzado_car):,} personas cruzadas por documento.".replace(",", "."))
                etiqueta_sel, col_sel_car = dims_detectadas[
                    st.selectbox(
                        "Cruzar % de aprobación académica por",
                        range(len(dims_detectadas)),
                        format_func=lambda i: dims_detectadas[i][0],
                        key="liff_car_dim_sel",
                    )
                ]
                cruzado_car["_PCT"] = pd.to_numeric(cruzado_car["pct_aprobacion_propio"], errors="coerce")
                g = cruzado_car.groupby(col_sel_car, observed=True)["_PCT"].mean().reset_index()
                with st.container(border=True):
                    fig = px.bar(
                        g, x=col_sel_car, y="_PCT",
                        title=f"% Aprobación promedio por {etiqueta_sel}", color_discrete_sequence=[VERDE],
                    )
                    fig.update_layout(xaxis_title=None, yaxis_title="% Aprobación")
                    st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_15")

        st.divider()
        with st.expander("Perfil genérico por columna (todas las preguntas de la encuesta)"):
            # _DOC/_POBLACION son columnas internas agregadas arriba para
            # el cruce por población -- se excluyen acá igual que en
            # Satisfacción.
            df_car_raw = df_car.drop(columns=["_DOC", "_POBLACION"], errors="ignore")
            st.markdown(f"**{len(df_car_raw):,}** filas, **{len(df_car_raw.columns)}** columnas.".replace(",", "."))
            categoricas_car = [c for c in df_car_raw.columns if df_car_raw[c].nunique(dropna=True) <= 20 and c != col_doc_car]
            if categoricas_car:
                col_sel2 = st.selectbox("Columna a explorar", categoricas_car, key="liff_car_col_sel")
                counts2 = df_car_raw[col_sel2].fillna("(vacío)").value_counts().reset_index()
                counts2.columns = [col_sel2, "cantidad"]
                fig = px.bar(counts2, x=col_sel2, y="cantidad", title=f"Distribución de {col_sel2}", color_discrete_sequence=[AZUL])
                fig.update_layout(xaxis_title=None, yaxis_title=None)
                st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_16")
            st.dataframe(df_car_raw, width="stretch")
