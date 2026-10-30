"""
EFE General › KPIs históricos -- migrado de "KPIs Históricos" de «Dash General EFE2» (n8n).

En n8n estos números estaban ESCRITOS A MANO en el código (HARDCODED_HISTORY, 52 filas) y la
consulta a BigQuery estaba desconectada. Ahora viven en la pestaña EFE_KPI_HISTORICO del Sheet de
operaciones: el equipo agrega una fila por proyecto cada mes y la página la toma en <=10 min.

Misma lógica que n8n:
  - Grupos Further Education / Employability / General EFE (utils/efe_metrics.GRUPOS o la columna
    'grupo' del Sheet).
  - Impactados = acumulado al corte (se muestra el del último mes elegido, no se suma).
  - Nuevos = diferencia de impactados contra el mes anterior (o la columna 'nuevos' si está llena),
    sumados en el periodo.
  - Retención / Aprobación / NPS / Satisfacción = promedio ponderado por impactados.
Botones: descargar (CSV/Excel), enviar por correo (webhook n8n) y reporte de riesgos (GitHub
'insights', con token en secrets -- en n8n estaba visible en el código de la página).
"""
import io

import pandas as pd
import plotly.express as px
import streamlit as st

from utils import efe_data as data
from utils import efe_metrics as m
from utils.efe_ui import eje_periodo, TODOS, inicio
from utils.ui import AMARILLO, AZUL, GRIS, NARANJA, VERDE, dark, kpi_row

correo_usuario = inicio("EFE · KPIs históricos", "Indicadores mensuales reportados · fuente: Sheet de operaciones, "
                                                 "pestaña EFE_KPI_HISTORICO")

try:
    hist = data.kpi_historico()
except Exception as exc:  # pestaña sin crear
    st.error(f"No pude leer la pestaña {data.PESTANA_HISTORICO}: {exc}. "
             "Créala con: python scripts\\efe_kpi_historico_setup.py --aplicar")
    st.stop()
if hist.empty:
    st.warning(f"La pestaña {data.PESTANA_HISTORICO} está vacía.")
    st.stop()

c1, c2, c3 = st.columns([1.3, 1.3, 2])
grupo = c1.radio("Grupo", ["Further Education", "Employability", "General EFE"], horizontal=True, key="efe_kpi_grupo")
h = hist if grupo == "General EFE" else hist[hist["grupo"] == grupo]
proyecto = c2.selectbox("Proyecto", [TODOS] + sorted(h["proyecto"].unique()), key="efe_kpi_proy")
if proyecto != TODOS:
    h = h[h["proyecto"] == proyecto]
meses = sorted(h["mes"].unique())
elegidos = c3.multiselect("Meses (vacío = todos)", meses, key="efe_kpi_meses")

resumen = m.resumen_historico(h)  # sobre TODO el historial: 'nuevos' necesita el mes anterior
if elegidos:
    resumen = resumen[resumen["mes"].isin(elegidos)]
if resumen.empty:
    st.info("Sin datos para este filtro.")
    st.stop()

titulo = proyecto if proyecto != TODOS else grupo
ultimo = resumen.iloc[-1]
varios = len(resumen) > 1
nota_prom = f"Prom. ponderado, {len(resumen)} meses" if varios else f"Dato de {ultimo['mes']}"
color = AZUL if grupo == "Employability" else NARANJA
st.markdown(f"### {titulo}")
kpi_row([
    ("Total impactados", m.fmt_num(ultimo["impactados"]), color, f"Corte a {ultimo['mes']}"),
    ("Nuevos impactados", m.fmt_num(resumen["nuevos"].sum()), VERDE,
     f"Total {len(resumen)} meses" if varios else f"Dato de {ultimo['mes']}"),
    ("% Retención", m.fmt_pct(m.promedio_ponderado(resumen["retencion"], resumen["impactados"])), VERDE, nota_prom),
    ("% Aprobación", m.fmt_pct(m.promedio_ponderado(resumen["aprobacion"], resumen["impactados"])), color, nota_prom),
    ("NPS", m.fmt_num(m.promedio_ponderado(resumen["nps"], resumen["impactados"]), 1), GRIS, nota_prom),
    ("Satisfacción", m.fmt_num(m.promedio_ponderado(resumen["satisfaccion"], resumen["impactados"]), 2), AMARILLO,
     nota_prom),
])

st.divider()
graficas = [("impactados", "Impactados", color, "line"), ("nuevos", "Nuevos", VERDE, "bar"),
            ("retencion", "% Retención", VERDE, "line"), ("aprobacion", "% Aprobación", color, "line"),
            ("nps", "NPS", GRIS, "line"), ("satisfaccion", "Satisfacción", AMARILLO, "line")]
for i in range(0, len(graficas), 2):
    cols = st.columns(2)
    for col, (campo, nombre, col_color, tipo) in zip(cols, graficas[i:i + 2]):
        with col:
            datos = resumen[["mes", campo]].rename(columns={campo: nombre})
            datos[nombre] = datos[nombre].round(2)
            fn = px.bar if tipo == "bar" else px.line
            extra = {} if tipo == "bar" else {"markers": True}
            fig = fn(datos, x="mes", y=nombre, title=nombre, text=nombre, color_discrete_sequence=[col_color], **extra)
            if tipo == "line":
                fig.update_traces(textposition="top center", cliponaxis=False)  # que no se corte la etiqueta en 100
            # Escala completa: los % (y el NPS) de 0 a 100 y la satisfacción de 0 a 5, para no exagerar
            # variaciones pequeñas (antes el eje se ajustaba solo al rango de los datos).
            if campo in ("retencion", "aprobacion"):
                fig.update_yaxes(range=[0, 100], dtick=20, ticksuffix="%")
            elif campo == "nps":
                fig.update_yaxes(range=[0, 100], dtick=20)
            elif campo == "satisfaccion":
                fig.update_yaxes(range=[0, 5], dtick=1)
            st.plotly_chart(dark(eje_periodo(fig), 300), use_container_width=True)

st.subheader("Detalle por proyecto y mes")
detalle = (h[h["mes"].isin(resumen["mes"])]
           [["mes", "proyecto", "grupo", "impactados", "nuevos", "retencion", "aprobacion", "nps", "satisfaccion"]]
           .sort_values(["mes", "proyecto"]))
st.dataframe(detalle, hide_index=True, use_container_width=True)

# ---------------------------------------------------------------------------- acciones
st.subheader("Exportar y compartir")
a1, a2, a3 = st.columns(3)
nombre_archivo = f"KPIs_EFE_{titulo.replace(' ', '_')}"
with a1:
    st.download_button("⬇️ Descargar CSV", detalle.to_csv(index=False).encode("utf-8-sig"),
                       f"{nombre_archivo}.csv", "text/csv", use_container_width=True)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        resumen.to_excel(xw, sheet_name="Resumen", index=False)
        detalle.to_excel(xw, sheet_name="Detalle", index=False)
    st.download_button("⬇️ Descargar Excel", buf.getvalue(), f"{nombre_archivo}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

periodo_txt = " / ".join(resumen["mes"]) if elegidos else "Año completo"
with a2, st.form("efe_kpi_correo", clear_on_submit=False):
    st.markdown("**✉️ Enviar reporte por correo**")
    texto = st.text_input("Destinatarios (separados por coma)", value=correo_usuario)
    if st.form_submit_button("Enviar reporte", use_container_width=True):
        destinatarios = [d.strip() for d in texto.replace(";", ",").split(",") if "@" in d]
        if not destinatarios:
            st.error("Escribe al menos un correo válido.")
        else:
            tabla_html = resumen.round(2).to_html(index=False, border=0, na_rep="–")
            html = (f"<h2>Reporte KPIs Kuepa — {titulo}</h2><p>Periodo: {periodo_txt}</p>{tabla_html}"
                    f"<p style='color:#888'>Enviado desde Kuepa Intelligence por {correo_usuario}</p>")
            ok, msg = data.enviar_correo(destinatarios, f"Reporte KPIs Kuepa — {titulo} | {periodo_txt}", html,
                                         {"grupo": grupo, "proyecto": proyecto, "periodo": periodo_txt,
                                          "filtro_meses": list(resumen["mes"]) if elegidos else []})
            (st.success if ok else st.error)(msg)

with a3, st.form("efe_kpi_riesgos"):
    st.markdown("**⚠️ Generar reporte de riesgos**")
    destino = st.text_input("Enviar a", value=correo_usuario)
    if st.form_submit_button("Generar reporte", use_container_width=True):
        if "@" not in destino:
            st.error("Correo no válido.")
        else:
            ok, msg = data.disparar_riesgos(destino.strip())
            (st.success if ok else st.error)(msg)
