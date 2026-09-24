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
     aprobación, nota, monto recaudado), tendencia mensual por población,
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
    aprobacion_counts,
    comparativo_kpis,
    enrich,
    enrich_crm,
    estado_academico_counts,
    estado_modulo_counts,
    estudiantes_por_programa,
    filtrar_corte_tecnicos_academico,
    filtrar_corte_tecnicos_funnel,
    funnel_kpis,
    funnel_por_categoria,
    kpis_overview,
    modulos_por_estado_pct_comparativo,
    nota_promedio_por_programa,
    tendencia_mensual_funnel,
    tendencia_mensual_poblacion,
)
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
        ("Monto recaudado", f"${kf['monto_recaudado']:,.0f}".replace(",", "."), AZUL, "Suma de matriculados"),
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
            kpis = kpis_overview(aca)

            st.subheader("Indicadores generales")
            _kpi_row(
                [
                    ("Estudiantes", str(kpis["estudiantes"]), NARANJA, ""),
                    ("Programas", str(kpis["programas"]), NARANJA, ""),
                    ("% Retención", f"{kpis['pct_retencion']:.1f}%", VERDE, "Activos / Total con match académico"),
                    ("% Aprobación", f"{kpis['pct_aprobacion']:.1f}%", NARANJA, "Sobre módulos con nota publicada"),
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
                df_ea = estado_academico_counts(aca)
                fig = px.pie(
                    df_ea, names="estado", values="cantidad", hole=0.55, title="Estado Académico",
                    color_discrete_sequence=[NARANJA, AZUL, GRIS], custom_data=["estado"],
                )
                fig.update_traces(textinfo="value+percent")
                st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_4")

            with g2, st.container(border=True):
                df_em = estado_modulo_counts(aca)
                fig = px.bar(
                    df_em, x="categoria", y="cantidad", title="Módulos: Cursados / En Curso / Próximos",
                    color="categoria", color_discrete_map={"Cursado": AZUL, "En Curso": AMARILLO, "Próximo": VERDE},
                    text="cantidad", custom_data=["categoria"],
                )
                fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title=None)
                st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_5")

            with g3, st.container(border=True):
                df_ap = aprobacion_counts(aca)
                fig = px.pie(
                    df_ap, names="categoria", values="cantidad", hole=0.55, title="Aprobación de Módulos",
                    color="categoria",
                    color_discrete_map={"Aprobado": VERDE, "No Aprobado": ROJO, "Pendiente de Nota": GRIS},
                    custom_data=["categoria"],
                )
                fig.update_traces(textinfo="value+percent")
                st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_6")

            st.write("")
            st.subheader("Por programa")
            g4, g5 = st.columns(2)
            with g4, st.container(border=True):
                df_ep = estudiantes_por_programa(aca)
                fig = px.bar(
                    df_ep, x="estudiantes", y="PROGRAMA", orientation="h", title="Estudiantes por Programa",
                    text="estudiantes", color_discrete_sequence=[NARANJA],
                )
                fig.update_layout(yaxis_title=None, xaxis_title=None)
                st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_7")
            with g5, st.container(border=True):
                df_np = nota_promedio_por_programa(aca)
                fig = px.bar(
                    df_np, x="nota_promedio", y="PROGRAMA", orientation="h", title="Nota Promedio por Programa",
                    text=df_np["nota_promedio"].round(2) if not df_np.empty else None,
                    color_discrete_sequence=[AZUL],
                )
                fig.update_layout(yaxis_title=None, xaxis_title=None)
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
                (
                    "Monto recaudado",
                    f"${ext['monto_recaudado']:,.0f} vs ${nac['monto_recaudado']:,.0f}".replace(",", "."),
                    AZUL, "",
                ),
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

            if col_grupo:
                with g2, st.container(border=True):
                    df_grp = pd.concat([df_sat[[col_grupo]], scores_num], axis=1)
                    df_grp = df_grp.groupby(col_grupo, observed=True)[SAT_COLUMNAS_SCORE].mean().reset_index()
                    df_grp_m = df_grp.melt(id_vars=col_grupo, var_name="categoria", value_name="promedio")
                    fig = px.bar(
                        df_grp_m, x=col_grupo, y="promedio", color="categoria", barmode="group",
                        title="Puntaje promedio por grupo",
                    )
                    fig.update_layout(xaxis_title=None, yaxis_title=None)
                    st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_11")
        elif tiene_scores:
            st.info(
                "Las columnas TUTORES/CONTENIDO/PLATAFORMA/SERVICIO están, pero no logré leerlas como "
                "números en las respuestas actuales -- revisa el formato en Sheets (¿vienen como texto?)."
            )

        # NPS
        if col_nps:
            nps_num = pd.to_numeric(df_sat[col_nps], errors="coerce").dropna()
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

        st.write("")
        if col_doc:
            st.success(f"Cruzando por documento con la columna **{col_doc}**.")
        else:
            st.warning(
                "No encontré una columna obvia de cédula/documento en esta hoja -- dime cuál es "
                "para poder cruzarla con Matrícula + Académico."
            )

        if col_doc:
            aca_full = academico_de(enrich_crm(df_raw))
            if not aca_full.empty:
                aca_full = filtrar_corte_tecnicos_academico(enrich(aca_full))
            if not aca_full.empty:
                resumen = academico_resumen_por_persona(aca_full)
                if not resumen.empty:
                    cruce = df_sat.copy()
                    cruce["_DOC"] = cruce[col_doc].astype(str).str.strip()
                    resumen["_DOC"] = resumen["CONTACT_DATA_DOCUMENT_ID"].astype(str).str.strip()
                    cruzado = cruce.merge(resumen, on="_DOC", how="inner")
                    if cruzado.empty:
                        st.caption("No encontré coincidencias de documento entre esta hoja y Matrícula + Académico todavía.")
                    else:
                        st.caption(f"{len(cruzado):,} personas cruzadas por documento.".replace(",", "."))
                        if tiene_scores and scores_num.notna().any().any():
                            # pct_aprobacion_propio viene con dtype "object" (mezcla de
                            # float y pd.NA) desde academico_resumen_por_persona() -- hay
                            # que forzarlo a numérico o .corr(numeric_only=True) la
                            # descarta silenciosamente y revienta el ["pct_aprobacion_propio"]
                            # de abajo con KeyError.
                            pct_num = pd.to_numeric(cruzado["pct_aprobacion_propio"], errors="coerce")
                            cruzado_scores = pd.concat(
                                [pct_num.rename("pct_aprobacion_propio"), scores_num.loc[cruzado.index]], axis=1
                            )
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
            st.markdown(f"**{len(df_sat):,}** filas, **{len(df_sat.columns)}** columnas.".replace(",", "."))
            categoricas = [c for c in df_sat.columns if df_sat[c].nunique(dropna=True) <= 20 and c != col_doc]
            if categoricas:
                col_sel = st.selectbox("Columna a explorar", categoricas, key="liff_sat_col_sel")
                counts = df_sat[col_sel].fillna("(vacío)").value_counts().reset_index()
                counts.columns = [col_sel, "cantidad"]
                fig = px.bar(counts, x=col_sel, y="cantidad", title=f"Distribución de {col_sel}", color_discrete_sequence=[AZUL])
                fig.update_layout(xaxis_title=None, yaxis_title=None)
                st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_13")
            st.dataframe(df_sat, width="stretch")

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

        if not dims_detectadas:
            st.warning(
                "No pude detectar ninguna de las 6 preguntas clave (estrato, estado civil, nivel "
                "escolar, empleabilidad, ingreso, género) por nombre -- puede que el texto de las "
                "preguntas haya cambiado. Revisa el perfil genérico más abajo."
            )
        else:
            st.caption("Perfil socioeconómico -- distribución de las respuestas.")
            cols_grid = st.columns(3)
            for i, (etiqueta, col) in enumerate(dims_detectadas):
                with cols_grid[i % 3], st.container(border=True):
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

        if col_doc_car and dims_detectadas:
            aca_full = academico_de(enrich_crm(df_raw))
            if not aca_full.empty:
                aca_full = filtrar_corte_tecnicos_academico(enrich(aca_full))
            if not aca_full.empty:
                resumen_car = academico_resumen_por_persona(aca_full)
                if not resumen_car.empty:
                    cruce_car = df_car.copy()
                    cruce_car["_DOC"] = cruce_car[col_doc_car].astype(str).str.strip()
                    resumen_car["_DOC"] = resumen_car["CONTACT_DATA_DOCUMENT_ID"].astype(str).str.strip()
                    cruzado_car = cruce_car.merge(resumen_car, on="_DOC", how="inner")
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
            st.markdown(f"**{len(df_car):,}** filas, **{len(df_car.columns)}** columnas.".replace(",", "."))
            categoricas_car = [c for c in df_car.columns if df_car[c].nunique(dropna=True) <= 20 and c != col_doc_car]
            if categoricas_car:
                col_sel2 = st.selectbox("Columna a explorar", categoricas_car, key="liff_car_col_sel")
                counts2 = df_car[col_sel2].fillna("(vacío)").value_counts().reset_index()
                counts2.columns = [col_sel2, "cantidad"]
                fig = px.bar(counts2, x=col_sel2, y="cantidad", title=f"Distribución de {col_sel2}", color_discrete_sequence=[AZUL])
                fig.update_layout(xaxis_title=None, yaxis_title=None)
                st.plotly_chart(_dark(fig), width="stretch", key="liff_chart_16")
            st.dataframe(df_car, width="stretch")
