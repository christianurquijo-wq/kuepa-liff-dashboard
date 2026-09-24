
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.iq_data import iq_limpiar_cache, load_iq_lecciones, load_iq_usuarios
from utils.iq_metrics import (
    PROGRAMAS,
    _self_check,
    banda_tiempo_por_programa,
    calidad_lecciones,
    calidad_solo_log_y_carga_masiva,
    cobertura_lecciones,
    desglose_por_nivel,
    enrich_lecciones,
    enrich_usuarios,
    fecha_de_corte,
    horas_por_area,
    id_sis_compartidos,
    kpis_recencia_por_programa,
    kpis_tiempo_por_programa,
    lecciones_pero_sin_acceso,
    lecciones_por_anio,
    matriz_recencia_uso,
    segmentos_por_programa,
    tabla_usuarios,
    tendencia_mensual_acceso,
    top_componentes,
)
from utils.ui import AMARILLO, AZUL, GRIS, NARANJA, ROJO, VERDE, badge, dark, inject_css, kpi_row

inject_css()

COLOR_PROGRAMA = {"IQP": AZUL, "IQS": NARANJA, "IQ512": VERDE}
COLOR_SEGMENTO = {
    "≤30 d": VERDE, "31–90": AZUL, "91–180": AMARILLO, "181–365": "#E67E22", ">365": ROJO, "Sin acceso": GRIS,
}

df_usuarios_raw, demo_usuarios = load_iq_usuarios()
df_lecciones_raw, demo_lecciones = load_iq_lecciones()

if df_usuarios_raw.empty:
    st.stop()  # load_iq_usuarios() ya mostró el st.error correspondiente

es_demo = demo_usuarios or demo_lecciones
if es_demo:
    st.warning(
        "**Datos de demostración** -- no hay credenciales configuradas en "
        "`.streamlit/secrets.toml` todavía, así que esta página muestra datos "
        "SINTÉTICOS (≈1 % de escala) solo para revisar que todo funciona. "
        "Ver el README para conectar las hojas reales.",
        icon="🧪",
    )

df_usuarios = enrich_usuarios(df_usuarios_raw)
df_lecciones = enrich_lecciones(df_lecciones_raw) if not df_lecciones_raw.empty else df_lecciones_raw

st.sidebar.header("Filtros -- IQ")
programas_sel = st.sidebar.multiselect("Programa", PROGRAMAS, default=PROGRAMAS, key="iq_programas")
excluir_carga_masiva = st.sidebar.toggle(
    "Excluir carga masiva IQ512",
    value=True,
    help=(
        "18.224 usuarios de IQ512 quedaron con MAX_LOG_DATE=2022-10-01 y sin "
        "acceso ni login registrado -- es una carga masiva de datos, no "
        "actividad real. Activo por defecto: no distorsiona la mediana de "
        "días sin acceso ni el % que 'nunca ingresó'. El total de 'Usuarios' "
        "del programa NO cambia con este interruptor."
    ),
    key="iq_excluir_carga_masiva",
)
excluir_internos = st.sidebar.toggle(
    "Excluir cuentas internas (lecciones)",
    value=True,
    help="Correos @iqsecundaria / @iqprimaria / @kuepa (cuentas de prueba/equipo) -- afecta solo la hoja de lecciones.",
    key="iq_excluir_internos",
)
if st.sidebar.button("🔄 Actualizar datos", key="iq_actualizar", help="Limpia el cache de 1 h y vuelve a leer las hojas ahora."):
    iq_limpiar_cache()
    st.rerun()

if not programas_sel:
    st.warning("Selecciona al menos un programa en la barra lateral para ver la página.")
    st.stop()

df_usuarios_f = df_usuarios[df_usuarios["PROGRAMA"].isin(programas_sel)]
df_lecciones_f = (
    df_lecciones[df_lecciones["Programa"].isin(programas_sel)] if not df_lecciones.empty else df_lecciones
)
if not df_lecciones_f.empty and excluir_internos and "Es_interno" in df_lecciones_f.columns:
    df_lecciones_f = df_lecciones_f[~df_lecciones_f["Es_interno"]]

if df_usuarios_f.empty:
    st.info("No hay usuarios para los programas seleccionados.")
    st.stop()

col_title, col_badge = st.columns([5, 1], vertical_alignment="center")
col_title.title("IQ -- Primaria, Secundaria y 512 Docentes")
if es_demo:
    col_badge.markdown(badge("DATOS DEMO", ROJO), unsafe_allow_html=True)
else:
    col_badge.markdown(badge(f"{len(df_usuarios_f):,} USUARIOS".replace(",", ".")), unsafe_allow_html=True)

corte = fecha_de_corte(df_usuarios_raw)
if corte:
    st.caption(
        f"Datos al {corte.strftime('%d/%m/%Y')} -- fecha reconstruida de los datos "
        f"(moda de EFFECTIVE_LAST_ACCESS + DAYS_SINCE_ACCESS), no la fecha de hoy. "
        f"Es una foto: la recencia envejece un día por cada día que pasa sin volver a pegar datos nuevos."
    )
else:
    st.caption("No se pudo reconstruir la fecha de corte (faltan EFFECTIVE_LAST_ACCESS/DAYS_SINCE_ACCESS).")

resumen_h = kpis_recencia_por_programa(df_usuarios_f, excluir_carga_masiva=excluir_carga_masiva)
total_usuarios = int(resumen_h["Usuarios"].sum())
total_base = int(resumen_h["Base recencia"].sum())
pct_30 = (df_usuarios_f["DAYS_SINCE_ACCESS"].le(30).sum() / total_base * 100) if total_base else 0.0
pct_90 = (df_usuarios_f["DAYS_SINCE_ACCESS"].le(90).sum() / total_base * 100) if total_base else 0.0
pct_nunca = (df_usuarios_f["segmento_recencia"].eq("Sin acceso").sum() / total_usuarios * 100) if total_usuarios else 0.0

with st.container(border=True):
    st.markdown("**Hallazgos clave**")
    st.markdown(
        f"- Hoy la plataforma tiene muy poca actividad: **{pct_30:.2f}%** de los usuarios entraron en los últimos 30 días "
        f"({pct_90:.1f}% en los últimos 90).\n"
        f"- **{pct_nunca:.0f}%** de los usuarios registrados nunca ha ingresado.\n"
        f"- El detalle de lecciones cubre solo una parte de los usuarios -- se lee como una muestra del consumo, no como el total "
        f"(ver pestaña 'Lecciones consumidas')."
    )

if not es_demo:
    fallas = [c for c in _self_check(df_usuarios_raw) if not c["ok"]]
    if fallas:
        with st.expander(f"⚠️ Autoverificación: {len(fallas)} valor(es) no coinciden con 04_hallazgos_y_valores_referencia.md", expanded=False):
            st.dataframe(pd.DataFrame(fallas), width="stretch", hide_index=True)
            st.caption("Puede ser una actualización real de los datos, o un problema en la última carga -- confirma antes de reportar el número al cliente.")

st.write("")
tab1, tab2, tab3, tab4 = st.tabs(["📊 Resumen y recencia", "⏱️ Uso y tiempo", "📚 Lecciones consumidas", "🔎 Usuarios y calidad de datos"])

with tab1:
    kpi_row(
        [
            ("Usuarios", f"{total_usuarios:,}".replace(",", "."), NARANJA, "Suma de los programas seleccionados"),
            ("Accedieron ≤30 d", f"{pct_30:.2f}%", VERDE, f"sobre {total_base:,} usuarios en la base de recencia".replace(",", ".")),
            ("Accedieron ≤90 d", f"{pct_90:.1f}%", AZUL, ""),
            ("Nunca ingresó", f"{pct_nunca:.0f}%", ROJO, "Sin registro en base de datos"),
        ]
    )
    st.write("")
    st.markdown("**KPIs por programa**")
    tabla_kpi = resumen_h.copy()
    for c in ["% ≤30 d", "% ≤90 d", "% nunca ingresó"]:
        tabla_kpi[c] = tabla_kpi[c].map(lambda v: f"{v:.1f}%")
    tabla_kpi["Mediana días sin acceso"] = tabla_kpi["Mediana días sin acceso"].map(lambda v: f"{v:.0f}" if pd.notna(v) else "—")
    st.dataframe(tabla_kpi, width="stretch", hide_index=True)

    st.write("")
    g1, g2 = st.columns(2)
    with g1, st.container(border=True):
        ancho = st.select_slider("Ancho del histograma (días)", options=[7, 15, 30, 90], value=30, key="iq_ancho_hist")
        dias_validos = df_usuarios_f["DAYS_SINCE_ACCESS"].dropna()
        if dias_validos.empty:
            st.info("No hay usuarios con fecha de acceso en esta selección.")
        else:
            max_dias = int(dias_validos.max()) + ancho
            bordes = np.arange(0, max_dias + ancho, ancho)
            etiquetas = [f"{int(bordes[i])}-{int(bordes[i+1])}" for i in range(len(bordes) - 1)]
            binned = pd.cut(dias_validos, bins=bordes, labels=etiquetas, include_lowest=True)
            conteo = binned.value_counts().reindex(etiquetas, fill_value=0).reset_index()
            conteo.columns = ["Rango (días)", "Usuarios"]
            conteo["%"] = conteo["Usuarios"] / len(dias_validos) * 100
            fig = px.bar(
                conteo, x="Rango (días)", y="Usuarios",
                title=f"La mayoría de los accesos quedaron hace mucho - días desde el último acceso",
                custom_data=["%"], color_discrete_sequence=[NARANJA],
            )
            fig.update_traces(hovertemplate="%{x}: %{y} usuarios (%{customdata[0]:.1f}%)")
            fig.update_layout(xaxis_title="Días desde el último acceso", yaxis_title="Usuarios")
            st.plotly_chart(dark(fig), width="stretch")
            st.caption(f"Excluye {df_usuarios_f['DAYS_SINCE_ACCESS'].isna().sum():,} usuarios en 'Sin acceso' (no tienen días que graficar).".replace(",", "."))
            with st.expander("Ver tabla"):
                st.dataframe(conteo, width="stretch", hide_index=True)

    with g2, st.container(border=True):
        seg = segmentos_por_programa(df_usuarios_f, excluir_carga_masiva=excluir_carga_masiva)
        fig2 = px.bar(
            seg, x="Programa", y="Porcentaje", color="Segmento", barmode="stack",
            title="IQ512 tiene la cola de inactividad más larga - actividad por programa (100%)",
            custom_data=["Usuarios"], color_discrete_map=COLOR_SEGMENTO,
            category_orders={"Segmento": list(COLOR_SEGMENTO.keys())},
        )
        fig2.update_traces(hovertemplate="%{customdata[0]} usuarios (%{y:.1f}%)")
        fig2.update_layout(yaxis_title="% de usuarios", xaxis_title=None)
        st.plotly_chart(dark(fig2), width="stretch")
        with st.expander("Ver tabla"):
            st.dataframe(seg, width="stretch", hide_index=True)

with tab2:
    st.caption("TIME_VIEW está en segundos en la fuente - aquí siempre se muestra en minutos/horas.")
    tiempo = kpis_tiempo_por_programa(df_usuarios_f)
    kpi_row(
        [
            (f"Tiempo promedio", f"{(df_usuarios_f['TIME_VIEW'].mean()/60):.0f} min", AZUL, "Todos los usuarios seleccionados, incluidos los de 0"),
            (f"Tiempo mediana", f"{(df_usuarios_f['TIME_VIEW'].median()/60):.0f} min", AZUL, ""),
            (f"Registros promedio", f"{df_usuarios_f['REGISTROS'].mean():.1f}", VERDE, "Filas en log_access por usuario"),
        ]
    )
    st.write("")
    tiempo_fmt = tiempo.copy()
    tiempo_fmt["Tiempo promedio (min)"] = tiempo_fmt["Tiempo promedio (min)"].map(lambda v: f"{v:.0f}")
    tiempo_fmt["Tiempo mediana (min)"] = tiempo_fmt["Tiempo mediana (min)"].map(lambda v: f"{v:.0f}")
    tiempo_fmt["Registros promedio"] = tiempo_fmt["Registros promedio"].map(lambda v: f"{v:.1f}")
    st.dataframe(tiempo_fmt, width="stretch", hide_index=True)

    st.write("")
    g1, g2 = st.columns(2)
    with g1, st.container(border=True):
        bt = banda_tiempo_por_programa(df_usuarios_f)
        fig3 = px.bar(
            bt, x="Banda", y="Usuarios", color="Programa", barmode="group",
            title="IQ512 concentra las sesiones más largas - usuarios por banda de tiempo",
            color_discrete_map=COLOR_PROGRAMA,
        )
        fig3.update_layout(xaxis_title=None, yaxis_title="Usuarios")
        st.plotly_chart(dark(fig3), width="stretch")
        with st.expander("Ver tabla"):
            st.dataframe(bt, width="stretch", hide_index=True)

    with g2, st.container(border=True):
        matriz = matriz_recencia_uso(df_usuarios_f, excluir_carga_masiva=excluir_carga_masiva)
        pivote = matriz.pivot(index="segmento_recencia", columns="banda_tiempo", values="Usuarios").fillna(0)
        fig4 = px.imshow(
            pivote, text_auto=True, aspect="auto", color_continuous_scale="Oranges",
            title="Cruce de actividad x tiempo de uso (conteo de usuarios)",
            labels=dict(x="Banda de tiempo", y="Segmento de actividad", color="Usuarios"),
        )
        st.plotly_chart(dark(fig4), width="stretch")
        with st.expander("Ver tabla"):
            st.dataframe(matriz, width="stretch", hide_index=True)

    st.write("")
    with st.container(border=True):
        tendencia = tendencia_mensual_acceso(df_usuarios_f, excluir_carga_masiva=excluir_carga_masiva)
        if tendencia.empty:
            st.info("No hay fechas de acceso para graficar la tendencia en esta selección.")
        else:
            fig5 = px.bar(
                tendencia, x="mes", y="Usuarios", color="Programa", barmode="group",
                title="El último acceso se concentra en pocos meses (picos mayo-junio en IQS, ciclos académicos)",
                color_discrete_map=COLOR_PROGRAMA,
            )
            fig5.update_layout(xaxis_title=None, yaxis_title="Usuarios (último acceso ese mes)")
            st.plotly_chart(dark(fig5), width="stretch")
            st.caption(
                "Cada barra es cuántos usuarios tuvieron su ÚLTIMO acceso registrado ese mes, no actividad continua. "
                + ("La carga masiva de IQ512 (2022-10) está excluida por el interruptor de la barra lateral." if excluir_carga_masiva else "Incluye la carga masiva de IQ512 (2022-10) -- ese pico no es actividad real.")
            )
            with st.expander("Ver tabla"):
                st.dataframe(tendencia, width="stretch", hide_index=True)

with tab3:
    if df_lecciones_f.empty:
        st.info("No hay filas de lecciones para los programas seleccionados (o la hoja de lecciones está vacía).")
    else:
        cobertura = cobertura_lecciones(df_usuarios_f, df_lecciones_f)
        st.markdown("**Cobertura** -- ver regla 8: la hoja de lecciones NO cubre a todos los usuarios.")
        cob_fmt = cobertura.copy()
        cob_fmt["Cobertura %"] = cob_fmt["Cobertura %"].map(lambda v: f"{v:.1f}%")
        cob_fmt["Horas (ajustadas)"] = cob_fmt["Horas (ajustadas)"].map(lambda v: f"{v:,.0f}".replace(",", "."))
        st.dataframe(cob_fmt, width="stretch", hide_index=True)
        st.caption(
            "Cobertura: "
            + " · ".join(
                f"{r['Programa']} {int(r['Usuarios con lecciones']):,}/{int(r['Usuarios totales']):,} usuarios".replace(",", ".")
                for _, r in cobertura.iterrows()
            )
            + f". {'Excluye' if excluir_internos else 'Incluye'} cuentas internas."
        )

        st.write("")
        g1, g2 = st.columns(2)
        with g1, st.container(border=True):
            area = horas_por_area(df_lecciones_f).head(12)
            fig6 = px.bar(
                area, x="Horas", y="Area_Conocimiento", orientation="h",
                title="Horas de lecciones por área de conocimiento (ajustadas, tope 4h/lección)",
                custom_data=["Usuarios", "Filas"], color="Programa", color_discrete_map=COLOR_PROGRAMA,
            )
            fig6.update_traces(hovertemplate="%{y}: %{x:.0f} h -- %{customdata[0]} usuarios")
            fig6.update_layout(yaxis_title=None, xaxis_title="Horas")
            st.plotly_chart(dark(fig6, height=420), width="stretch")
            with st.expander("Ver tabla"):
                st.dataframe(area, width="stretch", hide_index=True)

        with g2, st.container(border=True):
            top_c = top_componentes(df_lecciones_f, n=12)
            fig7 = px.bar(
                top_c, x="Filas", y="Componente_academico", orientation="h", color="Programa",
                title="Componentes académicos más consumidos (por filas)",
                color_discrete_map=COLOR_PROGRAMA, custom_data=["Usuarios"],
            )
            fig7.update_traces(hovertemplate="%{y}: %{x} filas -- %{customdata[0]} usuarios")
            fig7.update_layout(yaxis_title=None, xaxis_title="Filas")
            st.plotly_chart(dark(fig7, height=420), width="stretch")
            with st.expander("Ver tabla"):
                st.dataframe(top_c, width="stretch", hide_index=True)

        st.write("")
        st.markdown("**Por Nivel** -- regla 10: en IQ512 'Nivel' es curso/edición, no grado. Nunca se mezclan en el mismo gráfico.")
        g3, g4 = st.columns(2)
        with g3, st.container(border=True):
            niveles_grado = pd.concat(
                [desglose_por_nivel(df_lecciones_f, p).assign(Programa=p) for p in ["IQP", "IQS"] if p in programas_sel],
                ignore_index=True,
            ) if any(p in programas_sel for p in ["IQP", "IQS"]) else pd.DataFrame()
            if niveles_grado.empty:
                st.info("IQP/IQS no están en la selección de programas.")
            else:
                fig8 = px.bar(
                    niveles_grado, x="Nivel", y="Filas", color="Programa", barmode="group",
                    title="Lecciones por Grado (IQP/IQS)", color_discrete_map=COLOR_PROGRAMA,
                )
                fig8.update_layout(xaxis_title=None)
                st.plotly_chart(dark(fig8), width="stretch")
                with st.expander("Ver tabla"):
                    st.dataframe(niveles_grado, width="stretch", hide_index=True)

        with g4, st.container(border=True):
            if "IQ512" not in programas_sel:
                st.info("IQ512 no está en la selección de programas.")
            else:
                niveles_512 = desglose_por_nivel(df_lecciones_f, "IQ512")
                fig9 = px.bar(
                    niveles_512.head(10), x="Filas", y="Nivel", orientation="h",
                    title="IQ512 por curso/edición (no es un grado -- no unir ediciones del mismo curso)",
                    color_discrete_sequence=[VERDE],
                )
                fig9.update_layout(yaxis_title=None)
                st.plotly_chart(dark(fig9, height=380), width="stretch")
                with st.expander("Ver tabla"):
                    st.dataframe(niveles_512, width="stretch", hide_index=True)

        st.write("")
        g5, g6 = st.columns(2)
        with g5, st.container(border=True):
            anio = lecciones_por_anio(df_lecciones_f)
            fig10 = px.bar(
                anio, x="Anio", y="Filas", color="Programa", barmode="group",
                title="Lecciones por año de la vista (NO es línea de tiempo de actividad, ver regla 9)",
                color_discrete_map=COLOR_PROGRAMA,
            )
            fig10.update_layout(xaxis_title=None)
            st.plotly_chart(dark(fig10), width="stretch")
            with st.expander("Ver tabla"):
                st.dataframe(anio, width="stretch", hide_index=True)

        with g6, st.container(border=True):
            st.markdown("**Lecciones pero 'Sin acceso'**")
            st.caption("Usuarios con lecciones registradas pero sin ninguna fecha de acceso en la hoja 1 - las fechas de acceso no capturan todo el consumo.")
            cruce = lecciones_pero_sin_acceso(df_usuarios_f, df_lecciones_f)
            st.dataframe(cruce, width="stretch", hide_index=True)


with tab4:
    st.markdown("**Tabla de usuarios** (filtra/ordena por ID_SIS -- identificador de referencia, no es la llave real)")
    tabla = tabla_usuarios(df_usuarios_f, df_lecciones_f if not df_lecciones_f.empty else pd.DataFrame(columns=["Programa", "user_log_view"]))

    f1, f2, f3 = st.columns(3)
    filtro_sis = f1.text_input("Buscar ID_SIS", key="iq_filtro_sis")
    filtro_seg = f2.multiselect("Segmento", sorted(tabla["Segmento"].dropna().astype(str).unique()), key="iq_filtro_seg")
    orden_col = f3.selectbox("Ordenar por", tabla.columns.tolist(), index=tabla.columns.get_loc("Días sin acceso"), key="iq_orden_col")

    tabla_filtrada = tabla.copy()
    if filtro_sis:
        tabla_filtrada = tabla_filtrada[tabla_filtrada["ID_SIS"].astype(str).str.contains(filtro_sis, case=False, na=False)]
    if filtro_seg:
        tabla_filtrada = tabla_filtrada[tabla_filtrada["Segmento"].astype(str).isin(filtro_seg)]
    tabla_filtrada = tabla_filtrada.sort_values(orden_col, na_position="last")

    if tabla_filtrada.empty:
        st.info("Ningún usuario coincide con este filtro.")
    else:
        st.dataframe(tabla_filtrada, width="stretch", height=420, hide_index=True)
        LIMITE_DESCARGA = 50_000
        descarga = tabla_filtrada.head(LIMITE_DESCARGA)
        st.download_button(
            f"⬇️ Descargar CSV ({len(descarga):,} filas{' - limitado a 50.000' if len(tabla_filtrada) > LIMITE_DESCARGA else ''})".replace(",", "."),
            data=descarga.to_csv(index=False).encode("utf-8"),
            file_name="iq_usuarios_filtrado.csv",
            mime="text/csv",
            key="iq_descarga_csv",
        )

    st.write("")
    st.markdown("**Pruebas de calidad**")
    c1, c2, c3 = st.columns(3)
    idsis = id_sis_compartidos(df_usuarios_f)
    solo_log = calidad_solo_log_y_carga_masiva(df_usuarios_f)
    with c1:
        st.metric("Usuarios sin ID_SIS", f"{idsis['usuarios_sin_id_sis']:,}".replace(",", "."))
        st.metric("ID_SIS compartidos", f"{idsis['id_sis_compartidos']:,}".replace(",", "."), help=f"Involucran a {idsis['usuarios_involucrados']:,} usuarios distintos -- por esto no se cuenta por ID_SIS.".replace(",", "."))
    with c2:
        st.metric("'Solo log' (recencia aproximada)", f"{solo_log['solo_log']:,}".replace(",", "."))
        st.metric("Carga masiva IQ512", f"{solo_log['carga_masiva_iq512']:,}".replace(",", "."))
    with c3:
        if not df_lecciones_f.empty:
            cal = calidad_lecciones(df_lecciones_f)
            st.metric("Lecciones sin Horas", f"{cal['sin_horas']:,}".replace(",", "."))
            st.metric("Lecciones duplicadas", f"{cal['duplicados']:,}".replace(",", "."), help="Duplicados por (Programa, usuario, área, componente) -- deberían ser 0 si la deduplicación del SQL corrió bien.")
        else:
            st.caption("Sin datos de lecciones para calcular calidad.")
