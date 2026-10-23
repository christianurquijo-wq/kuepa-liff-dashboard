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
from utils.ops_metrics import (ORDEN_ESTADO, ORDEN_ORIGEN, duraciones, kpis, mapa_calor,
                               por_dia_estado, por_dia_origen, preparar, salud)
from utils.ui import AMARILLO, AZUL, GRIS, NARANJA, ROJO, VERDE, dark, hex_to_rgba, inject_css, kpi_row

inject_css()
requiere_login()

COLOR_ESTADO = {"EXITOSO": VERDE, "FALLIDO": ROJO, "TIMEOUT": AMARILLO}
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

# ------------------------------------------------------------------ Volumen diario
c1, c2 = st.columns(2)
with c1:
    d = por_dia_estado(df)
    fig = px.bar(d, x="dia", y="ejecuciones", color="estado",
                 category_orders={"estado": ORDEN_ESTADO}, color_discrete_map=COLOR_ESTADO,
                 title="Ejecuciones por día · resultado",
                 labels={"dia": "", "ejecuciones": "Ejecuciones", "estado": ""})
    fig.update_traces(marker_line_width=2, marker_line_color="#292929",
                      hovertemplate="%{x|%d-%b}<br>%{y} ejecuciones<extra>%{fullData.name}</extra>")
    st.plotly_chart(dark(fig), use_container_width=True)
with c2:
    d = por_dia_origen(df)
    fig = px.bar(d, x="dia", y="ejecuciones", color="origen_grupo",
                 category_orders={"origen_grupo": ORDEN_ORIGEN}, color_discrete_map=COLOR_ORIGEN,
                 title="Ejecuciones por día · origen",
                 labels={"dia": "", "ejecuciones": "Ejecuciones", "origen_grupo": ""})
    fig.update_traces(marker_line_width=2, marker_line_color="#292929",
                      hovertemplate="%{x|%d-%b}<br>%{y} ejecuciones<extra>%{fullData.name}</extra>")
    st.plotly_chart(dark(fig), use_container_width=True)

# ------------------------------------------------------------------ Duración y horario
c3, c4 = st.columns(2)
with c3:
    d = duraciones(df).sort_values("p95")
    # Etiqueta corta en el eje (máx. 34 caracteres); el nombre completo va en el tooltip.
    d["etiqueta"] = d["nombre"].map(lambda t: t if len(t) <= 34 else t[:33] + "…")
    fig = go.Figure()
    fig.add_bar(y=d["etiqueta"], x=d["p50"], orientation="h", name="Mediana (p50)",
                marker_color=NARANJA, customdata=d[["p95", "n", "nombre"]],
                hovertemplate="<b>%{customdata[2]}</b><br>p50: %{x:.0f} s · p95: %{customdata[0]:.0f} s"
                              "<br>%{customdata[1]} ejecuciones<extra></extra>")
    fig.add_scatter(y=d["etiqueta"], x=d["p95"], mode="markers", name="p95 (casi siempre por debajo)",
                    marker=dict(color="#FAFAFA", size=9, symbol="line-ns-open", line_width=2),
                    hoverinfo="skip")
    fig.update_layout(title="Duración por automatización · top 15 más lentas",
                      xaxis_title="segundos", yaxis_title="", yaxis_automargin=True,
                      legend_orientation="h", legend_y=-0.15)
    # Sin barra de herramientas: tapaba el título.
    st.plotly_chart(dark(fig, height=480), use_container_width=True, config={"displayModeBar": False})
with c4:
    m = mapa_calor(df)
    fig = go.Figure(go.Heatmap(
        z=m.values, x=[f"{h:02d}" for h in m.columns], y=DIAS,
        colorscale=[[0, hex_to_rgba(NARANJA, 0.06)], [1, NARANJA]], xgap=2, ygap=2,
        hovertemplate="%{y} %{x}:00<br>%{z} ejecuciones<extra></extra>",
        colorbar=dict(title="", thickness=10)))
    fig.update_layout(title="¿Cuándo corren? · día y hora (Bogotá)", yaxis_autorange="reversed")
    st.plotly_chart(dark(fig, height=440), use_container_width=True)

# ------------------------------------------------------------------ Salud por automatización
st.subheader("Salud por automatización")
st.caption("Primero lo que requiere atención: rachas de fallos y automatizaciones atrasadas "
           "(sin ejecutarse en más de 1,5× su frecuencia esperada). Calculado sobre el periodo filtrado.")
s = salud(df, catalogo, ahora)
if proyectos:
    s = s[s["proyecto"].isin(proyectos)]
vista = s.assign(
    ultima_ejecucion=s["ultima_ejecucion"].map(lambda t: t.strftime("%d-%b %H:%M") if pd.notna(t) else "—"),
    atrasada=s["atrasada"].map({True: "⚠ Sí", False: "No"}),
)[["nombre", "proyecto", "ultimo_estado", "ultima_ejecucion", "racha_fallos", "atrasada",
   "exito_pct", "ejecuciones", "frecuencia_esperada_h", "periodicidad_real_h", "dur_p50_seg", "dur_p95_seg"]]
st.dataframe(
    vista, hide_index=True, use_container_width=True,
    column_config={
        "nombre": "Automatización", "proyecto": "Proyecto", "ultimo_estado": "Último estado",
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
