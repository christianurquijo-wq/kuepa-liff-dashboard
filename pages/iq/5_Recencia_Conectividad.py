"""
IQ / Recencia y Conectividad por usuario -- oct-2026, a pedido de
Christian: "la hoja inicial de recencia y conectividad por usuario" con
los mapas de calor de tiempo de consumo y tiempo desde el último
logueo, como página ADICIONAL (no reemplaza nada de lo que ya está en
el menú de IQ).

Qué es esto exactamente: el histograma de recencia, el desglose por
segmento y el mapa de calor cruzado (recencia x tiempo de uso) YA
existían -- viven en pages/2_IQ.py ("Usuarios y lecciones (Sheets)"),
pestañas "Resumen y recencia" y "Uso y tiempo". No se borraron de ahí a
propósito (Christian pidió una hoja ADICIONAL, no una migración) -- esta
página los reutiliza tal cual, con toda la lógica de negocio en
utils/iq_metrics.py (mismas reglas numeradas del diccionario de datos,
sin duplicar código de cálculo, solo el layout).

Fuente: hojas de Sheets por USER_ID (utils/iq_data.py) -- es la fuente
"por usuario" (granular), distinta de active_usage_hours (agregada por
Alianza/mes, la que usan Análisis dinámico/Detalle de consumo/Cobertura).
Si en algún momento esto y la pestaña equivalente de "Usuarios y
lecciones (Sheets)" muestran números distintos, es porque uno de los dos
quedó desactualizado -- ambos llaman a las mismas funciones, así que no
debería pasar salvo cache viejo (usar el botón "Actualizar datos").

oct-2026 (2): cada sección (KPI, Última conexión, Tiempo de uso, Mapa de
calor, Análisis de último acceso) tiene su PROPIO selector de Programa,
independiente de las demás -- todos acotan DENTRO de lo que ya dejó pasar
el selector de la barra lateral (que sigue siendo el filtro de primer
nivel, junto con el interruptor de carga masiva). Además, "Análisis de
último acceso" (antes "Último acceso por mes") ahora tiene su propia
granularidad (Mes/Trimestre/Semestre/Año) y un deslizable de intervalo
que solo aparece en Mes.
"""
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from utils.iq_data import iq_limpiar_cache, load_iq_usuarios
from utils.iq_metrics import (
    PROGRAMAS,
    banda_tiempo_por_programa,
    enrich_usuarios,
    fecha_de_corte,
    kpis_recencia_por_programa,
    kpis_tiempo_por_programa,
    matriz_recencia_uso,
    segmentos_por_programa,
    tendencia_mensual_acceso,
)
from utils.iq_usage_hours import MESES_ES
from utils.ui import AMARILLO, AZUL, GRIS, NARANJA, ROJO, VERDE, badge, dark, inject_css, kpi_row

inject_css()

COLOR_PROGRAMA = {"IQP": AZUL, "IQS": NARANJA, "IQ512": VERDE}
# oct-2026: el código interno sigue siendo "IQ512" (así viene en la hoja de
# Sheets, vía utils/iq_metrics.py -- PROGRAMAS) -- Christian aclaró que el
# programa en realidad se llama solo "512"; PROGRAMA_LABEL/COLOR_PROGRAMA_DISPLAY
# son solo para lo que VE el usuario, nunca para filtrar. Ver misma nota en
# utils/iq_usage_hours.py.
PROGRAMA_LABEL = {"IQP": "IQP", "IQS": "IQS", "IQ512": "512"}
COLOR_PROGRAMA_DISPLAY = {PROGRAMA_LABEL[k]: v for k, v in COLOR_PROGRAMA.items()}
COLOR_SEGMENTO = {
    "≤30 d": VERDE, "31–90": AZUL, "91–180": AMARILLO, "181–365": "#E67E22", ">365": ROJO, "Sin acceso": GRIS,
}


def _selector_programa_seccion(key: str, opciones: list):
    """oct-2026: selector de Programa PROPIO por sección, a pedido de
    Christian -- acota DENTRO de lo que ya dejó pasar el selector de la
    barra lateral (que sigue siendo el filtro de primer nivel, con el
    interruptor de carga masiva). `opciones` es siempre `programas_sel`
    (la selección de la barra lateral), nunca la lista completa."""
    return st.multiselect(
        "Programa", opciones, default=opciones, key=key,
        format_func=lambda p: PROGRAMA_LABEL.get(p, p),
    )

# ---------------------------------------------------------------------------
# Carga + validación (solo la hoja de usuarios -- esta página no usa lecciones)
# ---------------------------------------------------------------------------
df_usuarios_raw, demo_usuarios = load_iq_usuarios()
if df_usuarios_raw.empty:
    st.stop()  # load_iq_usuarios() ya mostró el st.error correspondiente

if demo_usuarios:
    st.warning(
        "**Datos de demostración** -- no hay credenciales configuradas en "
        "`.streamlit/secrets.toml` todavía, así que esta página muestra datos "
        "SINTÉTICOS (≈1 % de escala) solo para revisar que todo funciona.",
        icon="🧪",
    )

df_usuarios = enrich_usuarios(df_usuarios_raw)

# ---------------------------------------------------------------------------
# Barra lateral -- mismos filtros/interruptor que "Usuarios y lecciones
# (Sheets)" (regla 6), con keys propios (iqrc_) para no chocar con esa
# página si las dos se visitan en la misma sesión.
# ---------------------------------------------------------------------------
st.sidebar.header("Filtros -- Actividad y Última Conexión")
programas_sel = st.sidebar.multiselect(
    "Programa", PROGRAMAS, default=PROGRAMAS, key="iqrc_programas",
    format_func=lambda p: PROGRAMA_LABEL.get(p, p),
)
excluir_carga_masiva = st.sidebar.toggle(
    "Excluir carga masiva 512",
    value=True,
    help=(
        "18.224 usuarios de 512 quedaron con MAX_LOG_DATE=2022-10-01 y sin "
        "acceso ni login registrado -- es una carga masiva de datos, no "
        "actividad real. Activo por defecto: no distorsiona la mediana de "
        "días sin acceso ni el % que 'nunca ingresó'. El total de 'Usuarios' "
        "del programa NO cambia con este interruptor."
    ),
    key="iqrc_excluir_carga_masiva",
)
if st.sidebar.button("🔄 Actualizar datos", key="iqrc_actualizar", help="Limpia el cache de 1 h y vuelve a leer las hojas ahora."):
    iq_limpiar_cache()
    st.rerun()

if not programas_sel:
    st.warning("Selecciona al menos un programa en la barra lateral para ver la página.")
    st.stop()

df_usuarios_f = df_usuarios[df_usuarios["PROGRAMA"].isin(programas_sel)]
if df_usuarios_f.empty:
    st.info("No hay usuarios para los programas seleccionados.")
    st.stop()

# ---------------------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------------------
col_title, col_badge = st.columns([5, 1], vertical_alignment="center")
col_title.title("Actividad y Última Conexión por usuario")
if demo_usuarios:
    col_badge.markdown(badge("DATOS DEMO", ROJO), unsafe_allow_html=True)
else:
    col_badge.markdown(badge(f"{len(df_usuarios_f):,} USUARIOS".replace(",", ".")), unsafe_allow_html=True)

corte = fecha_de_corte(df_usuarios_raw)
if corte:
    st.caption(
        f"Datos al {corte.strftime('%d/%m/%Y')} -- fecha reconstruida a partir de los "
        f"registros de acceso, no la fecha de hoy."
    )

st.write("")
prog_kpi_sel = _selector_programa_seccion("iqrc_prog_kpi", programas_sel)
df_kpi = df_usuarios_f[df_usuarios_f["PROGRAMA"].isin(prog_kpi_sel)]

if not prog_kpi_sel or df_kpi.empty:
    st.info("Selecciona al menos un programa para ver el KPI de cabecera.")
else:
    resumen_h = kpis_recencia_por_programa(df_kpi, excluir_carga_masiva=excluir_carga_masiva)
    total_usuarios = int(resumen_h["Usuarios"].sum())
    total_base = int(resumen_h["Base recencia"].sum())
    pct_30 = (df_kpi["DAYS_SINCE_ACCESS"].le(30).sum() / total_base * 100) if total_base else 0.0
    pct_90 = (df_kpi["DAYS_SINCE_ACCESS"].le(90).sum() / total_base * 100) if total_base else 0.0
    pct_nunca = (df_kpi["segmento_recencia"].eq("Sin acceso").sum() / total_usuarios * 100) if total_usuarios else 0.0

    st.write("")
    kpi_row(
        [
            ("Usuarios", f"{total_usuarios:,}".replace(",", "."), NARANJA, "Suma de los programas seleccionados"),
            ("Accedieron ≤30 d", f"{pct_30:.2f}%", VERDE, f"sobre {total_base:,} usuarios con fecha de acceso registrada".replace(",", ".")),
            ("Accedieron ≤90 d", f"{pct_90:.1f}%", AZUL, ""),
            ("Nunca ingresó", f"{pct_nunca:.0f}%", ROJO, "Segmento 'Sin acceso', ver regla 4"),
        ]
    )

    st.write("")
    st.markdown("**Indicadores por programa**")
    tabla_kpi = resumen_h.copy()
    tabla_kpi["Programa"] = tabla_kpi["Programa"].map(lambda p: PROGRAMA_LABEL.get(p, p))
    tabla_kpi = tabla_kpi.rename(columns={"Base recencia": "Con fecha de acceso"})
    for c in ["% ≤30 d", "% ≤90 d", "% nunca ingresó"]:
        tabla_kpi[c] = tabla_kpi[c].map(lambda v: f"{v:.1f}%")
    tabla_kpi["Mediana días sin acceso"] = tabla_kpi["Mediana días sin acceso"].map(lambda v: f"{v:.0f}" if pd.notna(v) else "—")
    st.dataframe(tabla_kpi, width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Última conexión -- tiempo desde el último logueo
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Última conexión -- días desde el último ingreso")
prog_conexion_sel = _selector_programa_seccion("iqrc_prog_conexion", programas_sel)
df_conexion = df_usuarios_f[df_usuarios_f["PROGRAMA"].isin(prog_conexion_sel)]

if not prog_conexion_sel or df_conexion.empty:
    st.info("Selecciona al menos un programa para ver esta sección.")
else:
    g1, g2 = st.columns(2)
    with g1, st.container(border=True):
        ancho = st.select_slider("Ancho del histograma (días)", options=[7, 15, 30, 90], value=30, key="iqrc_ancho_hist")
        dias_validos = df_conexion["DAYS_SINCE_ACCESS"].dropna()
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
                title=f"Días desde el último acceso (bins de {ancho} d)",
                custom_data=["%"], color_discrete_sequence=[NARANJA],
            )
            fig.update_traces(hovertemplate="%{x}: %{y} usuarios (%{customdata[0]:.1f}%)")
            fig.update_layout(xaxis_title="Días desde el último acceso", yaxis_title="Usuarios")
            st.plotly_chart(dark(fig), width="stretch", key="iqrc_chart_hist")
            st.caption(f"Excluye {df_conexion['DAYS_SINCE_ACCESS'].isna().sum():,} usuarios en 'Sin acceso' (no tienen días que graficar).".replace(",", "."))
            with st.expander("Ver tabla"):
                st.dataframe(conteo, width="stretch", hide_index=True)

    with g2, st.container(border=True):
        seg = segmentos_por_programa(df_conexion, excluir_carga_masiva=excluir_carga_masiva)
        seg["Programa"] = seg["Programa"].map(lambda p: PROGRAMA_LABEL.get(p, p))
        fig2 = px.bar(
            seg, x="Programa", y="Porcentaje", color="Segmento", barmode="stack",
            title="Última conexión por programa (100%)",
            custom_data=["Usuarios"], color_discrete_map=COLOR_SEGMENTO,
            category_orders={"Segmento": list(COLOR_SEGMENTO.keys())},
        )
        fig2.update_traces(hovertemplate="%{customdata[0]} usuarios (%{y:.1f}%)")
        fig2.update_layout(yaxis_title="% de usuarios", xaxis_title=None)
        st.plotly_chart(dark(fig2), width="stretch", key="iqrc_chart_segmentos")
        with st.expander("Ver tabla"):
            st.dataframe(seg, width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Tiempo de uso (TIME_VIEW)
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Tiempo de uso -- minutos y horas conectados")
st.caption("El tiempo de conexión se registra en segundos en la fuente y aquí siempre se muestra en minutos/horas. No es comparable con las horas de lecciones.")
prog_tiempo_sel = _selector_programa_seccion("iqrc_prog_tiempo", programas_sel)
df_tiempo = df_usuarios_f[df_usuarios_f["PROGRAMA"].isin(prog_tiempo_sel)]

if not prog_tiempo_sel or df_tiempo.empty:
    st.info("Selecciona al menos un programa para ver esta sección.")
else:
    tiempo = kpis_tiempo_por_programa(df_tiempo)
    kpi_row(
        [
            ("Tiempo promedio", f"{(df_tiempo['TIME_VIEW'].mean()/60):.0f} min", AZUL, "Todos los usuarios seleccionados, incluidos los de 0"),
            ("Tiempo mediana", f"{(df_tiempo['TIME_VIEW'].median()/60):.0f} min", AZUL, ""),
            ("Registros promedio", f"{df_tiempo['REGISTROS'].mean():.1f}", VERDE, "Filas en log_access por usuario"),
        ]
    )
    st.write("")
    tiempo_fmt = tiempo.copy()
    tiempo_fmt["Tiempo promedio (min)"] = tiempo_fmt["Tiempo promedio (min)"].map(lambda v: f"{v:.0f}")
    tiempo_fmt["Tiempo mediana (min)"] = tiempo_fmt["Tiempo mediana (min)"].map(lambda v: f"{v:.0f}")
    tiempo_fmt["Registros promedio"] = tiempo_fmt["Registros promedio"].map(lambda v: f"{v:.1f}")
    st.dataframe(tiempo_fmt, width="stretch", hide_index=True)

    st.write("")
    with st.container(border=True):
        bt = banda_tiempo_por_programa(df_tiempo)
        bt["Programa"] = bt["Programa"].map(lambda p: PROGRAMA_LABEL.get(p, p))
        fig3 = px.bar(
            bt, x="Banda", y="Usuarios", color="Programa", barmode="group",
            title="Usuarios por banda de tiempo de uso",
            color_discrete_map=COLOR_PROGRAMA_DISPLAY,
        )
        fig3.update_layout(xaxis_title=None, yaxis_title="Usuarios")
        st.plotly_chart(dark(fig3), width="stretch", key="iqrc_chart_banda")
        with st.expander("Ver tabla"):
            st.dataframe(bt, width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Mapa de calor -- última conexión x tiempo de uso, el que Christian pidió
# de vuelta.
# ---------------------------------------------------------------------------
st.write("")
with st.container(border=True):
    prog_mapa_sel = _selector_programa_seccion("iqrc_prog_mapa", programas_sel)
    df_mapa = df_usuarios_f[df_usuarios_f["PROGRAMA"].isin(prog_mapa_sel)]

    if not prog_mapa_sel or df_mapa.empty:
        st.info("Selecciona al menos un programa para ver el mapa de calor.")
    else:
        matriz = matriz_recencia_uso(df_mapa, excluir_carga_masiva=excluir_carga_masiva)
        pivote = matriz.pivot(index="segmento_recencia", columns="banda_tiempo", values="Usuarios").fillna(0)
        pivote.index.name = "Última conexión"
        pivote.columns.name = "Tiempo de uso"
        fig4 = px.imshow(
            pivote, text_auto=True, aspect="auto", color_continuous_scale="Oranges",
            title="Última conexión x tiempo de uso (cantidad de usuarios)",
            labels=dict(x="Banda de tiempo de uso", y="Última conexión", color="Usuarios"),
        )
        st.plotly_chart(dark(fig4), width="stretch", key="iqrc_chart_heatmap")
        with st.expander("Ver tabla"):
            st.dataframe(
                matriz.rename(columns={"segmento_recencia": "Última conexión", "banda_tiempo": "Tiempo de uso"}),
                width="stretch", hide_index=True,
            )

st.write("")
with st.container(border=True):
    st.markdown("**Análisis de último acceso**")
    prog_ultimo_sel = _selector_programa_seccion("iqrc_prog_ultimo", programas_sel)
    df_ultimo = df_usuarios_f[df_usuarios_f["PROGRAMA"].isin(prog_ultimo_sel)]
    tendencia = tendencia_mensual_acceso(df_ultimo, excluir_carga_masiva=excluir_carga_masiva) if prog_ultimo_sel else pd.DataFrame()

    if not prog_ultimo_sel or tendencia.empty:
        st.info("No hay fechas de acceso para graficar en esta selección.")
    else:
        tendencia["Programa"] = tendencia["Programa"].map(lambda p: PROGRAMA_LABEL.get(p, p))
        tendencia["Anio"] = tendencia["mes"].dt.year
        tendencia["Mes"] = tendencia["mes"].dt.month

        gu1, gu2 = st.columns([1, 3])
        with gu1:
            grano_ult_label = st.selectbox(
                "Granularidad", ["Mes", "Trimestre", "Semestre", "Año"], index=0, key="iqrc_grano_ultimo",
            )

        # -- sub-período dentro del año, según la granularidad elegida ------
        if grano_ult_label == "Mes":
            tendencia["_sub"] = tendencia["Mes"].apply(lambda m: MESES_ES[m - 1][:3])
            tendencia["_orden"] = tendencia["Anio"] * 12 + tendencia["Mes"]
            tendencia["_label"] = tendencia["_sub"] + " " + tendencia["Anio"].astype(str)
        elif grano_ult_label == "Trimestre":
            trimestre = ((tendencia["Mes"] - 1) // 3) + 1
            tendencia["_orden"] = tendencia["Anio"] * 4 + trimestre
            tendencia["_label"] = "T" + trimestre.astype(str) + " " + tendencia["Anio"].astype(str)
        elif grano_ult_label == "Semestre":
            semestre = ((tendencia["Mes"] - 1) // 6) + 1
            tendencia["_orden"] = tendencia["Anio"] * 2 + semestre
            tendencia["_label"] = "S" + semestre.astype(str) + " " + tendencia["Anio"].astype(str)
        else:  # Año
            tendencia["_orden"] = tendencia["Anio"]
            tendencia["_label"] = tendencia["Anio"].astype(str)

        # -- deslizable de intervalo, SOLO para granularidad Mes ------------
        if grano_ult_label == "Mes":
            periodos_ult = tendencia[["_orden", "_label"]].drop_duplicates().sort_values("_orden")
            opciones_ult = periodos_ult["_label"].tolist()
            if len(opciones_ult) > 1:
                with gu2:
                    m_desde, m_hasta = st.select_slider(
                        "Intervalo de tiempo", options=opciones_ult,
                        value=(opciones_ult[0], opciones_ult[-1]), key="iqrc_slider_ultimo",
                    )
                orden_ini = periodos_ult.loc[periodos_ult["_label"] == m_desde, "_orden"].iloc[0]
                orden_fin = periodos_ult.loc[periodos_ult["_label"] == m_hasta, "_orden"].iloc[0]
                tendencia = tendencia[(tendencia["_orden"] >= orden_ini) & (tendencia["_orden"] <= orden_fin)]

        tendencia_g = (
            tendencia.groupby(["_orden", "_label", "Programa"], as_index=False)["Usuarios"].sum()
            .sort_values("_orden")
        )
        orden_x_ult = tendencia_g["_label"].unique().tolist()

        fig5 = px.bar(
            tendencia_g, x="_label", y="Usuarios", color="Programa", barmode="group",
            title="Análisis de último acceso",
            color_discrete_map=COLOR_PROGRAMA_DISPLAY,
        )
        fig5.update_xaxes(categoryorder="array", categoryarray=orden_x_ult)
        fig5.update_layout(xaxis_title=None, yaxis_title=f"Usuarios (último acceso, por {grano_ult_label.lower()})")
        st.plotly_chart(dark(fig5), width="stretch", key="iqrc_chart_tendencia")
        st.caption(
            "Cada barra es cuántos usuarios tuvieron su ÚLTIMO acceso registrado en ese período, no actividad continua. "
            + ("La carga masiva de 512 (2022-10) está excluida por el interruptor de la barra lateral." if excluir_carga_masiva else "Incluye la carga masiva de 512 (2022-10) -- ese pico no es actividad real.")
        )
        with st.expander("Ver tabla"):
            st.dataframe(
                tendencia_g.rename(columns={"_label": "Período"})[["Período", "Programa", "Usuarios"]],
                width="stretch", hide_index=True,
            )
