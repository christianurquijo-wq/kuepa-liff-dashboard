"""
Operaciones -- Análisis de ejecuciones.

Fuente: LOG_EJECUCIONES (una fila por script ejecutado, GitHub o n8n) cruzada
con CATALOGO. Definiciones de cada métrica en utils/ops_metrics.py.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.ops_auth import requiere_login
from utils.ops_data import TZ, leer_catalogo, leer_log, refrescar
from utils.ops_metrics import (ORDEN_ORIGEN, duracion_diaria, duraciones, exito_diario,
                               fallos_por_automatizacion, kpis, mapa_calor, por_dia_origen, preparar, salud)
from utils.ui import AMARILLO, AZUL, GRIS, NARANJA, ROJO, VERDE, dark, hex_to_rgba, inject_css, kpi_row

inject_css()
requiere_login()

COLOR_ORIGEN = {"Botón panel": NARANJA, "Programada": AZUL, "Manual / otra": GRIS}
DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

col_t, col_b = st.columns([5, 1], vertical_alignment="center")
col_t.title("Análisis de ejecuciones")
if col_b.button("↻ Actualizar", use_container_width=True):
    refrescar()
    st.rerun()

catalogo = leer_catalogo()
base = preparar(leer_log(), catalogo)
ahora = pd.Timestamp(datetime.now(TZ))
if base.empty:
    st.info("Aún no hay ejecuciones registradas en LOG_EJECUCIONES. "
            "Dispara una automatización desde el Panel de control para empezar.")
    st.stop()

# ------------------------------------------------------------------ Filtros (una fila)
f1, f2, f3, f4 = st.columns([1.2, 1, 1.4, 1.4])
rango = f1.selectbox("Periodo", ["Últimos 7 días", "Últimos 30 días", "Últimos 90 días", "Todo"], index=1)
plataformas = f2.multiselect("Plataforma", sorted(base["plataforma"].unique()), placeholder="Todas")
proyectos = f3.multiselect("Proyecto", sorted(base["proyecto"].unique()), placeholder="Todos")
origenes = f4.multiselect("Origen", ORDEN_ORIGEN, placeholder="Todos")

df = base
dias = {"Últimos 7 días": 7, "Últimos 30 días": 30, "Últimos 90 días": 90}.get(rango)
if dias:
    df = df[df["fecha_inicio"] >= ahora - pd.Timedelta(days=dias)]
if plataformas:
    df = df[df["plataforma"].isin(plataformas)]
if proyectos:
    df = df[df["proyecto"].isin(proyectos)]
if origenes:
    df = df[df["origen_grupo"].isin(origenes)]

if df.empty:
    st.info("No hay ejecuciones con esos filtros.")
    st.stop()

# ------------------------------------------------------------------ KPIs
k = kpis(df)
kpi_row([
    ("Ejecuciones", f"{k['total']:,}".replace(",", "."), NARANJA,
     f"{k['por_boton']} por botón · {k['programadas']} programadas"),
    ("Tasa de éxito", f"{k['exito_pct']:.1f}%", VERDE if k["exito_pct"] >= 95 else AMARILLO, "EXITOSO / total"),
    ("Fallidas", f"{k['fallidas']}", ROJO, "incluye timeouts"),
    ("Duración mediana", f"{k['dur_mediana']:.0f} s", AZUL, "por script"),
    ("En falla ahora", f"{k['en_falla']}", ROJO if k["en_falla"] else GRIS, "última ejecución no exitosa"),
])
st.write("")

# ------------------------------------------------------------------ Utilidades de gráficos
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
SIN_BARRA = {"displayModeBar": False}  # la barra de herramientas tapaba los títulos


def fecha_es(t) -> str:
    return f"{t.day} {MESES[t.month - 1]}"


def ejes_fecha(fig, dias_serie: pd.Series, max_marcas: int = 8) -> None:
    """Etiquetas del eje X en español (Plotly las pone en inglés) sin amontonarlas."""
    dias_serie = pd.Series(pd.to_datetime(dias_serie)).drop_duplicates().sort_values()
    paso = max(1, -(-len(dias_serie) // max_marcas))
    marcas = dias_serie.iloc[::paso]
    fig.update_xaxes(tickvals=list(marcas), ticktext=[fecha_es(t) for t in marcas], title="", tickangle=0)


def titulo(texto: str, ayuda: str = "") -> None:
    st.markdown(f"**{texto}**")
    if ayuda:
        st.caption(ayuda)


def mostrar(fig, alto: int = 340) -> None:
    fig = dark(fig, height=alto)
    fig.update_layout(margin=dict(t=36, b=10, l=10, r=10), hoverlabel=dict(font_size=13),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.08)", zeroline=False)
    fig.update_xaxes(showgrid=False)
    st.plotly_chart(fig, use_container_width=True, config=SIN_BARRA)


# ------------------------------------------------------------------ Ejecuciones y éxito por día
META_EXITO = 95
d = exito_diario(df)
d["fecha"] = d["dia"].map(fecha_es)
titulo("Ejecuciones y tasa de éxito por día",
       "Barras: cuántos scripts/flujos corrieron (cada script de un lote cuenta). Línea: % que terminó bien. "
       f"La línea punteada es el promedio de 7 días (ponderado por volumen) y la gris la meta de {META_EXITO} %.")
fig = go.Figure()
fig.add_bar(x=d["dia"], y=d["ejecuciones"], name="Ejecuciones", marker_color=hex_to_rgba(AZUL, 0.55),
            marker_line_width=0, yaxis="y",
            customdata=d[["fecha", "exitosas", "fallidas"]],
            hovertemplate="<b>%{customdata[0]}</b><br>%{y} ejecuciones · %{customdata[1]} bien · "
                          "%{customdata[2]} fallidas<extra></extra>")
fig.add_scatter(x=d["dia"], y=d["exito_pct"], name="% de éxito del día", yaxis="y2", mode="lines+markers",
                line=dict(color=NARANJA, width=2), marker=dict(size=8, line=dict(width=2, color="#0E1117")),
                connectgaps=False, customdata=d[["fecha"]],
                hovertemplate="<b>%{customdata[0]}</b><br>Éxito del día: %{y:.1f} %<extra></extra>")
fig.add_scatter(x=d["dia"], y=d["exito_pct_movil"], name="Promedio 7 días", yaxis="y2", mode="lines",
                line=dict(color=NARANJA, width=2, dash="dot"), customdata=d[["fecha"]],
                hovertemplate="<b>%{customdata[0]}</b><br>Promedio 7 días: %{y:.1f} %<extra></extra>")
fig.add_hline(y=META_EXITO, yref="y2", line=dict(color=GRIS, width=1, dash="dash"),
              annotation_text=f"Meta {META_EXITO} %", annotation_position="bottom right",
              annotation_font_color=GRIS)
fig.update_layout(
    bargap=0.35, hovermode="x unified",
    yaxis=dict(title="Ejecuciones", rangemode="tozero"),
    yaxis2=dict(title="% de éxito", overlaying="y", side="right", range=[0, 105], ticksuffix=" %",
                tickvals=[0, 25, 50, 75, 100], showgrid=False),
)
ejes_fecha(fig, d["dia"], max_marcas=12)
mostrar(fig, alto=380)

# ------------------------------------------------------------------ Origen por día · dónde falla
c1, c2 = st.columns(2)
with c1:
    titulo("¿Quién las dispara?", "Ejecuciones por día según su origen.")
    o = por_dia_origen(df)
    o["fecha"] = o["dia"].map(fecha_es)
    fig = px.bar(o, x="dia", y="ejecuciones", color="origen_grupo",
                 category_orders={"origen_grupo": ORDEN_ORIGEN}, color_discrete_map=COLOR_ORIGEN,
                 labels={"dia": "", "ejecuciones": "Ejecuciones", "origen_grupo": ""}, custom_data=["fecha"])
    fig.update_traces(marker_line_width=2, marker_line_color="#0E1117",
                      hovertemplate="<b>%{customdata[0]}</b><br>%{fullData.name}: %{y}<extra></extra>")
    ejes_fecha(fig, o["dia"], max_marcas=6)
    mostrar(fig)
with c2:
    titulo("¿Dónde falla más?", "Top 10 automatizaciones por número de fallos en el periodo (incluye timeouts).")
    fa = fallos_por_automatizacion(df)
    if fa.empty:
        st.success("Sin fallos en el periodo filtrado.")
    else:
        fa = fa.sort_values("fallidas")
        fa["etiqueta"] = fa["nombre"].map(lambda t: t if len(t) <= 34 else t[:33] + "…")
        fig = go.Figure(go.Bar(
            y=fa["etiqueta"], x=fa["fallidas"], orientation="h", marker_color=ROJO, marker_line_width=0,
            text=fa["fallidas"], textposition="outside", cliponaxis=False,
            customdata=fa[["nombre", "total", "fallo_pct"]],
            hovertemplate="<b>%{customdata[0]}</b><br>%{x} fallos de %{customdata[1]} ejecuciones "
                          "(%{customdata[2]:.0f} %)<extra></extra>"))
        fig.update_layout(xaxis_title="Fallos", yaxis_title="", yaxis_automargin=True, bargap=0.35)
        mostrar(fig)

# ------------------------------------------------------------------ Duración y horario
c3, c4 = st.columns(2)
with c3:
    titulo("¿Cuánto tardan?", "Top 15 más lentas: la barra es la duración típica (mediana) y la marca "
                              "blanca el p95 (casi siempre terminan antes de ese punto).")
    du = duraciones(df).sort_values("p95")
    du["etiqueta"] = du["nombre"].map(lambda t: t if len(t) <= 34 else t[:33] + "…")
    fig = go.Figure()
    fig.add_bar(y=du["etiqueta"], x=du["p50"], orientation="h", name="Mediana", marker_color=NARANJA,
                marker_line_width=0, customdata=du[["p95", "n", "nombre"]],
                hovertemplate="<b>%{customdata[2]}</b><br>Mediana: %{x:.0f} s · p95: %{customdata[0]:.0f} s"
                              "<br>%{customdata[1]} ejecuciones<extra></extra>")
    fig.add_scatter(y=du["etiqueta"], x=du["p95"], mode="markers", name="p95",
                    marker=dict(color="#FAFAFA", size=10, symbol="line-ns-open", line_width=2), hoverinfo="skip")
    fig.update_layout(xaxis_title="segundos", yaxis_title="", yaxis_automargin=True, bargap=0.35)
    mostrar(fig, alto=460)
with c4:
    titulo("¿Cuándo corren?", "Ejecuciones por día de la semana y hora (Bogotá).")
    m = mapa_calor(df)
    fig = go.Figure(go.Heatmap(
        z=m.values, x=[f"{h:02d}" for h in m.columns], y=DIAS,
        colorscale=[[0, hex_to_rgba(NARANJA, 0.06)], [1, NARANJA]], xgap=2, ygap=2,
        hovertemplate="%{y} · %{x}:00<br>%{z} ejecuciones<extra></extra>",
        colorbar=dict(title="", thickness=10)))
    fig.update_layout(yaxis_autorange="reversed", xaxis_title="hora")
    mostrar(fig, alto=460)

# ------------------------------------------------------------------ Tendencia de duración
titulo("Tendencia de duración", "Duración por día de una automatización (solo ejecuciones exitosas). "
                                "Si la línea sube semana a semana, algo se está volviendo lento.")
opciones_dur = du.sort_values("p95", ascending=False)["nombre"].tolist() or sorted(df["nombre"].unique())
otras = [n for n in sorted(df["nombre"].unique()) if n not in opciones_dur]
elegida = st.selectbox("Automatización", opciones_dur + otras, key="an_tendencia",
                       label_visibility="collapsed")
t = duracion_diaria(df, elegida)
if len(t) < 2:
    st.info("Se necesitan al menos 2 días con ejecuciones exitosas para ver la tendencia.")
else:
    t["fecha"] = t["dia"].map(fecha_es)
    fig = go.Figure()
    fig.add_scatter(x=t["dia"], y=t["maximo"], name="Máxima del día", mode="lines",
                    line=dict(color=hex_to_rgba(AZUL, 0.55), width=2, dash="dot"), customdata=t[["fecha"]],
                    hovertemplate="<b>%{customdata[0]}</b><br>Máxima: %{y:.0f} s<extra></extra>")
    fig.add_scatter(x=t["dia"], y=t["p50"], name="Mediana del día", mode="lines+markers",
                    line=dict(color=AZUL, width=2), marker=dict(size=8, line=dict(width=2, color="#0E1117")),
                    customdata=t[["fecha", "n"]],
                    hovertemplate="<b>%{customdata[0]}</b><br>Mediana: %{y:.0f} s · %{customdata[1]} "
                                  "ejecuciones<extra></extra>")
    fig.update_layout(yaxis=dict(title="segundos", rangemode="tozero"), hovermode="x unified")
    ejes_fecha(fig, t["dia"])
    mostrar(fig)

# ------------------------------------------------------------------ Salud por automatización
st.divider()
st.subheader("Salud por automatización")
st.caption("Primero lo que requiere atención: rachas de fallos y automatizaciones atrasadas "
           "(sin ejecutarse en más de 1,5× su frecuencia esperada). Calculado sobre el periodo filtrado.")
s = salud(df, catalogo, ahora)
if proyectos:
    s = s[s["proyecto"].isin(proyectos)]
vista = s.assign(
    ultima_ejecucion=s["ultima_ejecucion"].map(lambda t: t.strftime("%d-%b %H:%M") if pd.notna(t) else "—"),
    atrasada=s["atrasada"].map({True: "⚠ Sí", False: "No"}),
)[["nombre", "proyecto", "periodicidad", "ultimo_estado", "ultima_ejecucion", "racha_fallos", "atrasada",
   "exito_pct", "ejecuciones", "frecuencia_esperada_h", "periodicidad_real_h", "dur_p50_seg", "dur_p95_seg"]]
st.dataframe(
    vista, hide_index=True, use_container_width=True,
    column_config={
        "nombre": "Automatización", "proyecto": "Proyecto", "periodicidad": "Periodicidad",
        "ultimo_estado": "Último estado",
        "ultima_ejecucion": "Última ejecución",
        "racha_fallos": st.column_config.NumberColumn("Racha de fallos", format="%d"),
        "atrasada": "Atrasada",
        "exito_pct": st.column_config.ProgressColumn("Éxito", format="%.0f%%", min_value=0, max_value=100),
        "ejecuciones": st.column_config.NumberColumn("Ejecuciones", format="%d"),
        "frecuencia_esperada_h": st.column_config.NumberColumn("Cada (h) esperado", format="%.0f"),
        "periodicidad_real_h": st.column_config.NumberColumn("Cada (h) real", format="%.1f"),
        "dur_p50_seg": st.column_config.NumberColumn("p50 (s)", format="%.0f"),
        "dur_p95_seg": st.column_config.NumberColumn("p95 (s)", format="%.0f"),
    },
)

# ------------------------------------------------------------------ Fallos recientes
fallos = df[~df["exito"]].sort_values("fecha_inicio", ascending=False).head(30)
st.subheader(f"Fallos recientes ({len(fallos)})")
if fallos.empty:
    st.success("Sin fallos en el periodo filtrado.")
for _, f in fallos.iterrows():
    with st.expander(f"✖ {f['fecha_inicio']:%d-%b %H:%M} · {f['nombre']} · {f['estado']} · {f['origen_grupo']}"):
        st.markdown(f"Disparado por **{f['disparado_por'] or '—'}** · duración {f['duracion_seg']:.0f} s"
                    + (f" · [ver en GitHub/n8n]({f['run_url']})" if f["run_url"] else ""))
        st.code(f["error"] or "(sin detalle)", language="text")

# ------------------------------------------------------------------ Datos
with st.expander("Ver / descargar datos del periodo"):
    columnas = ["fecha_inicio", "nombre", "proyecto", "plataforma", "origen_grupo", "disparado_por",
                "estado", "duracion_seg", "lote", "run_url"]
    st.dataframe(df[columnas].sort_values("fecha_inicio", ascending=False), hide_index=True,
                 use_container_width=True)
    st.download_button("Descargar CSV", df[columnas].to_csv(index=False).encode("utf-8-sig"),
                       file_name="ejecuciones.csv", mime="text/csv")
