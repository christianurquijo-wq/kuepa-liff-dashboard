
import pandas as pd
import plotly.express as px
import streamlit as st

from utils.iq_data import load_iq_lecciones, load_iq_usuarios
from utils.iq_metrics import cobertura_lecciones, enrich_usuarios, horas_por_area, top_componentes
from utils.iq_usage_hours import (
    COLOR_PROGRAMA_DISPLAY,
    etiqueta_programa,
    load_mensual_alianza_app,
    load_mensual_alianza_grado,
    load_mensual_alianza_region,
    load_mensual_alianza_rol,
    load_regiones_educativas_coords,
    usage_hours_actualizado_al,
)
from utils.ui import badge, dark, inject_css

inject_css()

st.markdown(badge("IQ · Detalle de consumo", "#29B6F6"), unsafe_allow_html=True)
st.title("Detalle de consumo")
st.caption(f"Datos de uso al {usage_hours_actualizado_al()} (fuente: `active_usage_hours`, BigQuery).")

df_grado = load_mensual_alianza_grado()
df_rol = load_mensual_alianza_rol()
df_region = load_mensual_alianza_region()
df_app = load_mensual_alianza_app()
coords = load_regiones_educativas_coords()

if df_grado.empty:
    st.error("No encontré los resúmenes de `data/iq/usage_hours/`.")
    st.stop()

alianzas_disp = sorted(df_grado["Programa"].unique())
alianzas_sel = st.multiselect(
    "Alianza", alianzas_disp, default=alianzas_disp, key="detalle_alianza", format_func=etiqueta_programa
)

tab_grado, tab_rol, tab_zona, tab_plataforma, tab_recurso = st.tabs(
    ["Por Grado", "Por Rol", "Zona geográfica", "Plataforma", "Por Recurso (lecciones)"]
)

with tab_grado:
    f = df_grado[df_grado["Programa"].isin(alianzas_sel)].groupby(["Programa", "Grado"], observed=True).agg(
        usuarios_activos=("usuarios_activos", "sum"), horas_totales=("horas_totales", "sum")
    ).reset_index()
    f["Programa"] = f["Programa"].map(etiqueta_programa)
    fig = px.bar(
        f, x="Grado", y="usuarios_activos", color="Programa", barmode="group",
        color_discrete_map=COLOR_PROGRAMA_DISPLAY, title="Usuarios activos por Grado",
    )
    st.plotly_chart(dark(fig), width="stretch")
    with st.expander("Ver tabla"):
        st.dataframe(f.sort_values(["Programa", "usuarios_activos"], ascending=[True, False]), hide_index=True, width="stretch")

with tab_rol:
    f = df_rol[df_rol["Programa"].isin(alianzas_sel)].groupby(["Programa", "roles_string"], observed=True).agg(
        usuarios_activos=("usuarios_activos", "sum"), horas_totales=("horas_totales", "sum")
    ).reset_index()
    f["Programa"] = f["Programa"].map(etiqueta_programa)
    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(
            f, x="roles_string", y="usuarios_activos", color="Programa", barmode="group",
            color_discrete_map=COLOR_PROGRAMA_DISPLAY, title="Usuarios activos por Rol",
        )
        st.plotly_chart(dark(fig), width="stretch")
    with c2:
        tot_rol = f.groupby("roles_string", observed=True)["usuarios_activos"].sum().reset_index()
        fig = px.pie(tot_rol, names="roles_string", values="usuarios_activos", title="Distribución de roles (todas las alianzas seleccionadas)")
        st.plotly_chart(dark(fig), width="stretch")
    with st.expander("Ver tabla"):
        st.dataframe(f.sort_values(["Programa", "usuarios_activos"], ascending=[True, False]), hide_index=True, width="stretch")

with tab_zona:
    f = df_region[df_region["Programa"].isin(alianzas_sel)].groupby(["region_norm"], observed=True).agg(
        usuarios_activos=("usuarios_activos", "sum"), horas_totales=("horas_totales", "sum")
    ).reset_index().sort_values("usuarios_activos", ascending=False)

    n_sin_ubicacion = f.loc[f["region_norm"] == "Sin ubicación", "usuarios_activos"].sum()
    if n_sin_ubicacion:
        st.caption(
            f"ℹ️ {int(n_sin_ubicacion):,}".replace(",", ".") +
            " registros no tienen centro educativo asignado (\"Sin ubicación\") -- no se intenta geocodificar, quedan como su propio segmento."
        )

    fig = px.bar(
        f[f["region_norm"] != "Sin ubicación"].head(20),
        x="region_norm", y="usuarios_activos", title="Usuarios activos por Regional Educativa (top 20)",
    )
    fig.update_layout(xaxis_title="", showlegend=False)
    st.plotly_chart(dark(fig), width="stretch")

    if not coords.empty:
        mapa = f.merge(coords, on="region_norm", how="inner")
        if not mapa.empty:
            # px.scatter_map (Plotly >=5.24) reemplaza a scatter_mapbox (quitado
            # en Plotly 6+) -- usa tiles MapLibre, no necesita token de Mapbox.
            fig = px.scatter_map(
                mapa, lat="latitud", lon="longitud", size="usuarios_activos",
                hover_name="region_norm", hover_data={"usuarios_activos": True, "latitud": False, "longitud": False},
                zoom=6.5, height=420, title="Mapa de usuarios activos por Regional Educativa",
            )
            fig.update_layout(map_style="carto-darkmatter", margin=dict(t=45, b=10, l=10, r=10),
                               paper_bgcolor="rgba(0,0,0,0)", font_color="#FAFAFA")
            st.plotly_chart(fig, width="stretch")
    with st.expander("Ver tabla"):
        st.dataframe(f, hide_index=True, width="stretch")

with tab_plataforma:
    f = df_app[df_app["Programa"].isin(alianzas_sel)].groupby(["Programa", "app"], observed=True).agg(
        usuarios_activos=("usuarios_activos", "sum"), horas_totales=("horas_totales", "sum")
    ).reset_index()
    f["Programa"] = f["Programa"].map(etiqueta_programa)
    fig = px.bar(
        f, x="Programa", y="usuarios_activos", color="app", barmode="group",
        title="Usuarios activos por Plataforma (LMS vs App móvil)",
    )
    st.plotly_chart(dark(fig), width="stretch")
    st.caption(
        "La app móvil no tiene registros antes de junio de 2023 en los datos exportados -- "
        "coincide con el lanzamiento de esa plataforma, no es un hueco de exportación (ver página Cobertura)."
    )
    with st.expander("Ver tabla"):
        st.dataframe(f.sort_values(["Programa", "usuarios_activos"], ascending=[True, False]), hide_index=True, width="stretch")

with tab_recurso:
    st.caption(
        "Esta pestaña usa la hoja `IQ_lecciones` (Google Sheets), no `active_usage_hours` -- "
        "es la única fuente que trae Recurso / Área de conocimiento / Componente académico."
    )
    df_usuarios, demo_u = load_iq_usuarios()
    df_lecciones, demo_l = load_iq_lecciones()
    if demo_u or demo_l:
        st.warning("⚠️ Mostrando datos de DEMOSTRACIÓN (no están las credenciales/hojas reales configuradas).")
    if df_lecciones.empty:
        st.info("No hay datos de lecciones disponibles.")
    else:
        df_usuarios_e = enrich_usuarios(df_usuarios)
        cob = cobertura_lecciones(df_usuarios_e, df_lecciones)
        st.markdown("**Cobertura de lecciones (obligatoria antes de leer los gráficos de abajo)**")
        st.dataframe(cob, hide_index=True, width="stretch")

        c1, c2 = st.columns(2)
        with c1:
            ha = horas_por_area(df_lecciones)
            ha["Programa"] = ha["Programa"].map(etiqueta_programa)
            fig = px.bar(ha.head(15), x="Area_Conocimiento", y="Horas", color="Programa",
                         color_discrete_map=COLOR_PROGRAMA_DISPLAY, title="Horas por Área de conocimiento (top 15)")
            st.plotly_chart(dark(fig), width="stretch")
        with c2:
            tc = top_componentes(df_lecciones, n=15)
            tc["Programa"] = tc["Programa"].map(etiqueta_programa)
            fig = px.bar(tc, x="Componente_academico", y="Filas", color="Programa",
                         color_discrete_map=COLOR_PROGRAMA_DISPLAY, title="Top 15 componentes académicos (por # de lecciones)")
            st.plotly_chart(dark(fig), width="stretch")
        with st.expander("Ver tabla de recursos"):
            st.dataframe(df_lecciones.assign(Programa=df_lecciones["Programa"].map(etiqueta_programa)), width="stretch")
