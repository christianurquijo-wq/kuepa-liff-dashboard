"""
Operaciones -- Ahorro de tiempo (horas de trabajo manual que ahorran las automatizaciones).

PÚBLICA (sin login): solo muestra horas por automatización/proyecto/responsable; no muestra
quién disparó cada ejecución ni los mensajes de error. Reglas en utils/ops_ahorro.py.
Fuentes: LOG_EJECUCIONES + LOG_HISTORICO (historial reconstruido) cruzadas con el CATALOGO
(columnas min_ahorro_ejecucion / tope_ejecuciones_dia / ahorro_estado / ahorro_supuesto, que
crea y llena scripts/ops_ahorro_catalogo.py).
"""
from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils import ops_ahorro as a
from utils.ops_data import TZ, leer_catalogo, leer_log, refrescar
from utils.ui import AMARILLO, AZUL, GRIS, NARANJA, VERDE, dark, inject_css, kpi_row

inject_css()
PALETA = [NARANJA, AZUL, VERDE, AMARILLO, "#A569BD", "#E74C3C", GRIS, "#48C9B0", "#F1948A", "#5DADE2"]


def fmt(x: float, dec: int = 0) -> str:
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


col_t, col_b = st.columns([5, 1], vertical_alignment="center")
col_t.title("Ahorro de tiempo")
col_t.caption("Horas de trabajo manual que el equipo deja de hacer gracias a las automatizaciones")
if col_b.button("↻ Actualizar", use_container_width=True):
    refrescar()
    a.leer_historico.clear()
    st.rerun()

catalogo = leer_catalogo()
if "min_ahorro_ejecucion" not in catalogo.columns:
    st.warning("El CATALOGO todavía no tiene la columna min_ahorro_ejecucion. "
               "Créala con: python scripts\\ops_ahorro_catalogo.py --aplicar")
base = a.preparar(leer_log(), a.leer_historico(), catalogo)
if base.empty:
    st.info("Aún no hay ejecuciones registradas.")
    st.stop()

# ------------------------------------------------------------------ filtros
hoy = pd.Timestamp(datetime.now(TZ).date())
f1, f2, f3, f4 = st.columns([1.6, 1.4, 1.5, 1.5])
gran = f1.radio("Ver por", a.PERIODOS, index=2, horizontal=True, key="ah_gran")
dmin = base["dia"].min().date()
rango = f2.date_input("Rango", value=(dmin, hoy.date()), min_value=dmin, max_value=hoy.date(),
                      format="DD/MM/YYYY", key="ah_rango")
desde, hasta = (pd.Timestamp(rango[0]), pd.Timestamp(rango[1])) if len(rango) == 2 else (pd.Timestamp(dmin), hoy)
proyectos = f3.multiselect("Proyecto", sorted(base["proyecto"].unique()), placeholder="Todos", key="ah_proy")
origenes = f4.multiselect("Origen", ["Programada", "Botón panel", "Manual / otra"], placeholder="Todos", key="ah_orig")

filtrado = base
if proyectos:
    filtrado = filtrado[filtrado["proyecto"].isin(proyectos)]
if origenes:
    filtrado = filtrado[filtrado["origen_grupo"].isin(origenes)]
df = filtrado[filtrado["dia"].between(desde, hasta)]
if df.empty:
    st.info("Sin ejecuciones en este filtro.")
    st.stop()

# ------------------------------------------------------------------ KPIs
k = a.kpis(df, desde, hasta)
mes_actual = hoy.to_period("M").start_time
mes_ant = (mes_actual - pd.DateOffset(months=1))
h_mes = filtrado[(filtrado["dia"] >= mes_actual)]["horas"].sum()
h_ant_mismo_punto = filtrado[(filtrado["dia"] >= mes_ant) & (filtrado["dia"] <= mes_ant + (hoy - mes_actual))]["horas"].sum()
delta = h_mes - h_ant_mismo_punto
kpi_row([
    ("Horas ahorradas", fmt(k["horas"], 1), NARANJA, f"{fmt(k['ejecuciones_suman'])} ejecuciones exitosas que suman"),
    ("Jornadas de 8 h", fmt(k["jornadas"], 1), VERDE, "Días de trabajo de una persona"),
    ("Personas equivalentes", fmt(k["fte"], 2), AZUL, "Tiempo completo en el rango (días hábiles × 8 h)"),
    ("Este mes", fmt(h_mes, 1) + " h", AMARILLO,
     f"{'+' if delta >= 0 else '−'}{fmt(abs(delta), 1)} h vs. mismo punto del mes anterior"),
    ("Automatizaciones que ahorran", fmt(k["automatizaciones"]), GRIS,
     f"{k['sin_estimar']} sin estimar" if k["sin_estimar"] else "Todas estimadas"),
])
if (df["ahorro_estado"] == "Estimado").any():
    st.caption("Los minutos por ejecución son **estimados** hasta que el responsable los valide en el CATALOGO "
               "(columna ahorro_estado = Validado). Solo suman ejecuciones exitosas y hasta el tope diario.")

# Un color fijo por proyecto (mismo en todas las gráficas), del que más ahorra al que menos.
orden_proy = a.ranking(df, "proyecto")["proyecto"].tolist()
COLOR_PROY = {p: PALETA[i % len(PALETA)] for i, p in enumerate(orden_proy)}

# ------------------------------------------------------------------ tendencia
st.subheader("Tendencia")
apilar = st.toggle("Separar por proyecto", value=True, key="ah_apilar")
serie = a.por_periodo(df, gran, "proyecto" if apilar else None)
total = a.por_periodo(df, gran).assign(Acumulado=lambda x: x["horas"].cumsum())
fig = go.Figure()
if apilar:
    for p in orden_proy:  # solo proyectos que ahorran algo en el rango
        x = serie[serie["proyecto"] == p]
        fig.add_bar(x=x["Etiqueta"], y=x["horas"].round(1), name=p, marker_color=COLOR_PROY[p])
else:
    fig.add_bar(x=total["Etiqueta"], y=total["horas"].round(1), name="Horas", marker_color=NARANJA,
                text=total["horas"].round(1), textposition="outside")
fig.add_scatter(x=total["Etiqueta"], y=total["Acumulado"].round(1), name="Acumulado", mode="lines+markers",
                line=dict(color="#FAFAFA", width=2), yaxis="y2")
fig.update_layout(barmode="stack", title=f"Horas ahorradas por {gran.lower()} y acumulado",
                  yaxis=dict(title="Horas en el periodo"),
                  yaxis2=dict(title="Acumulado (h)", overlaying="y", side="right", showgrid=False, rangemode="tozero"),
                  legend=dict(orientation="h", y=-0.18))
fig.update_xaxes(type="category", categoryorder="array", categoryarray=list(total["Etiqueta"]))
st.plotly_chart(dark(fig, 420), use_container_width=True)

st.markdown("**Horas por proyecto y periodo**")
st.dataframe(a.matriz(df, gran), use_container_width=True)

# ------------------------------------------------------------------ rankings
st.subheader("¿Qué ahorra más?")
c1, c2 = st.columns([1.4, 1])
with c1:
    r = a.ranking(df, "nombre").head(15)
    if not r.empty:
        fig = px.bar(r, x="horas", y="nombre", orientation="h", text=r["horas"].round(1),
                     title="Top 15 automatizaciones (horas)", color_discrete_sequence=[NARANJA],
                     hover_data={"ejecuciones": True})
        fig.update_layout(yaxis={"categoryorder": "total ascending", "title": None}, xaxis_title="Horas")
        st.plotly_chart(dark(fig, 460), use_container_width=True)
with c2:
    r = a.ranking(df, "proyecto")
    if not r.empty:
        fig = px.pie(r, names="proyecto", values="horas", hole=0.55, title="Por proyecto",
                     color="proyecto", color_discrete_map=COLOR_PROY)
        fig.update_traces(textinfo="percent+label")
        st.plotly_chart(dark(fig, 460), use_container_width=True)

c3, c4 = st.columns(2)
with c3:
    r = a.ranking(df, "responsable")
    if not r.empty:
        fig = px.bar(r, x="responsable", y="horas", text=r["horas"].round(1), title="Por responsable",
                     color_discrete_sequence=[AZUL])
        fig.update_layout(xaxis_title=None, yaxis_title="Horas")
        st.plotly_chart(dark(fig, 340), use_container_width=True)
with c4:
    r = a.ranking(df, "origen_grupo")
    if not r.empty:
        fig = px.pie(r, names="origen_grupo", values="horas", hole=0.55, title="Programadas vs. disparadas a mano",
                     color="origen_grupo",
                     color_discrete_map={"Programada": AZUL, "Botón panel": NARANJA, "Manual / otra": GRIS})
        st.plotly_chart(dark(fig, 340), use_container_width=True)

# ------------------------------------------------------------------ detalle
st.subheader("Detalle por automatización")
tabla = a.tabla_automatizaciones(df)
st.dataframe(
    tabla, hide_index=True, use_container_width=True,
    column_config={
        "nombre": "Automatización", "proyecto": "Proyecto", "ejecuciones": "Ejecuciones",
        "exitosas": "Exitosas", "suman": "Suman", "sobre_tope": "Sobre tope",
        "min_ejecucion": st.column_config.NumberColumn("Min/ejecución", format="%.0f"),
        "tope": st.column_config.NumberColumn("Tope/día", format="%.0f"),
        "estado": "Estimación", "horas": st.column_config.NumberColumn("Horas", format="%.1f"),
    })

sin = tabla[tabla["estado"] == a.ESTADO_SIN]
if not sin.empty:
    with st.expander(f"⚠️ {len(sin)} automatizaciones con ejecuciones pero sin minutos estimados (no suman)"):
        st.dataframe(sin[["nombre", "proyecto", "ejecuciones", "exitosas"]], hide_index=True, use_container_width=True)
        st.caption("Pon sus minutos en el CATALOGO (columna min_ahorro_ejecucion).")

if (df["fuente"] == "Historial reconstruido").any():
    n_hist = int((df["fuente"] == "Historial reconstruido").sum())
    st.caption(f"Incluye {fmt(n_hist)} ejecuciones del historial reconstruido (GitHub Actions y n8n, antes de la "
               "bitácora). En los lotes de ese periodo solo se sabe si el lote completo salió bien: si falló, "
               "sus scripts no suman.")

# ------------------------------------------------------------------ descarga
detalle = df[["fecha_inicio", "nombre", "proyecto", "responsable", "plataforma", "origen_grupo", "estado",
              "fuente", "min_unit", "motivo", "minutos"]].copy()
detalle["fecha_inicio"] = detalle["fecha_inicio"].dt.tz_localize(None)
detalle = detalle.rename(columns={"fecha_inicio": "Fecha", "nombre": "Automatización", "proyecto": "Proyecto",
                                  "responsable": "Responsable", "plataforma": "Plataforma", "origen_grupo": "Origen",
                                  "estado": "Estado", "fuente": "Fuente", "min_unit": "Min por ejecución",
                                  "motivo": "¿Suma?", "minutos": "Minutos ahorrados"})
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="openpyxl") as xw:
    a.matriz(df, gran).to_excel(xw, sheet_name=f"Horas por {gran.lower()}")
    tabla.to_excel(xw, sheet_name="Por automatización", index=False)
    detalle.to_excel(xw, sheet_name="Ejecuciones", index=False)
st.download_button("⬇️ Descargar Excel (resumen + ejecuciones)", buf.getvalue(),
                   f"Ahorro_tiempo_{desde:%Y%m%d}_{hasta:%Y%m%d}.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
