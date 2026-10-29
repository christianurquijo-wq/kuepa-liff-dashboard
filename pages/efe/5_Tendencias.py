"""
EFE General › Tendencias -- reemplaza "Data Mensualizada" de n8n y agrega lo que pidió
Christian: ver los KPIs por día, semana, mes o trimestre y cómo cambian.

Dos tipos de indicador, dos maneras de agrupar:
  - STOCK (cuántas personas están en un estado: impactados, activos, retención, contratados).
    Salen de las fotos guardadas: mensual (*_APPEND, 1 por mes, hasta antes de la foto diaria)
    y diaria (*_DIARIO, la toma EFE/Foto_diaria_EFE.py cada noche). Por periodo se muestra el
    CORTE: la última foto del periodo (una semana muestra cómo cerró la semana).
  - FLUJO (cosas que pasan en una fecha: nuevos por fecha de ingreso, encuestas de satisfacción
    y de caracterización). Salen del estado actual con su propia fecha, así que tienen historia
    completa hacia atrás. Por periodo se SUMAN (o se promedian, en NPS y satisfacción).
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from utils import efe_data as data
from utils import efe_metrics as m
from utils.efe_ui import eje_periodo, PALETA, TODOS, inicio
from utils.ui import AMARILLO, AZUL, GRIS, NARANJA, ROJO, VERDE, dark

inicio("EFE · Tendencias", "Evolución de los indicadores por día, semana, mes o trimestre")

with st.spinner("Consultando BigQuery..."):
    serie_seg, hay_diaria = data.serie_seguimiento()
    serie_emp = data.serie_empleabilidad()
    seg = data.seguimiento()
    sat = data.satisfaccion()
    car = data.caracterizacion()

if not hay_diaria:
    st.info("La foto diaria todavía no tiene datos (empieza la primera noche que corra Foto_diaria_EFE.py). "
            "Mientras tanto, los indicadores de estado se ven con la foto mensual.")

# ---------------------------------------------------------------------------- controles
c1, c2, c3, c4 = st.columns([1.3, 1, 1.2, 1.4])
gran = c1.radio("Ver por", list(m.PERIODOS), index=2, horizontal=True, key="efe_ten_gran")
proyectos = sorted(set(serie_seg["Proyecto"].dropna()) | set(seg["Proyecto"].dropna()))
proyecto = c2.selectbox("Proyecto", [TODOS] + proyectos, key="efe_ten_proy")
programas = sorted(serie_seg.loc[(serie_seg["Proyecto"] == proyecto) & (serie_seg["Programa"] != "(Todos)"),
                                 "Programa"].dropna().unique()) if proyecto != TODOS else []
programa = c3.selectbox("Programa", [TODOS] + programas, key="efe_ten_prog", disabled=proyecto == TODOS)

fechas_todas = pd.concat([serie_seg["Fecha"], serie_emp["Fecha"], seg["fecha_ingreso"], sat["fecha"], car["fecha"]]).dropna()
if fechas_todas.empty:
    st.warning("No hay fechas para graficar.")
    st.stop()
fmin, fmax = fechas_todas.min().date(), max(fechas_todas.max().date(), pd.Timestamp.today().date())
rango = c4.date_input("Rango", value=(max(fmin, (pd.Timestamp(fmax) - pd.DateOffset(months=12)).date()), fmax),
                      min_value=fmin, max_value=fmax, format="DD/MM/YYYY", key="efe_ten_rango")
desde, hasta = (pd.Timestamp(rango[0]), pd.Timestamp(rango[1])) if len(rango) == 2 else (pd.Timestamp(fmin), pd.Timestamp(fmax))


def en_rango(df: pd.DataFrame, col: str) -> pd.DataFrame:
    return df[df[col].between(desde, hasta + pd.Timedelta(days=1), inclusive="left")]


def etiqueta(p: pd.Series) -> pd.Series:
    if gran == "Día":
        return p.dt.strftime("%d/%m/%Y")
    if gran == "Semana":
        return "Sem " + p.dt.strftime("%d/%m/%Y")
    if gran == "Mes":
        return p.dt.strftime("%Y-%m")
    return p.dt.year.astype(str) + "-T" + p.dt.quarter.astype(str)


def variacion(df: pd.DataFrame, columnas: list[str], es_pct: set) -> None:
    """Último periodo vs el anterior."""
    if len(df) < 2:
        return
    ult, ant = df.iloc[-1], df.iloc[-2]
    cols = st.columns(len(columnas))
    for col, c in zip(cols, columnas):
        v, a = ult[c], ant[c]
        if pd.isna(v):
            col.metric(c, "–")
            continue
        delta = None if pd.isna(a) else v - a
        if c in es_pct:
            col.metric(c, m.fmt_pct(v), None if delta is None else f"{delta:+.1f} pp".replace(".", ","),
                       delta_color="inverse" if "Deserción" in c else "normal")
        else:
            col.metric(c, m.fmt_num(v), None if delta is None else f"{delta:+,.0f}".replace(",", "."),
                       delta_color="inverse" if c in ("Desertores", "Matrícula no exitosa") else "normal")
    st.caption(f"Variación: {ult['Etiqueta']} frente a {ant['Etiqueta']}.")


# ---------------------------------------------------------------------------- 1. académico (stock)
st.subheader("Académico")
x = serie_seg.copy()
if proyecto == TODOS:
    x = x[x["Programa"] == "(Todos)"]
else:
    x = x[(x["Proyecto"] == proyecto) & (x["Programa"] == ("(Todos)" if programa == TODOS else programa))]
x = en_rango(x, "Fecha")
numericas = ["personas", "impactados", "activos", "finalizados", "desertores", "matricula_no_exitosa",
             "insc_impactadas", "insc_retenidas", "insc_desertoras", "insc_aprobadas", "insc_reprobadas"]
if x.empty:
    st.info("Sin fotos de seguimiento en este rango.")
else:
    tot = x.groupby("Fecha", as_index=False)[numericas].sum()
    tot["Origen"] = x.groupby("Fecha")["Origen"].first().values
    tot = m.corte_por_periodo(tot, gran, claves=[]).sort_values("Periodo")
    tot = m.tasas_serie(tot)
    tot["Etiqueta"] = etiqueta(tot["Periodo"])
    tot = tot.rename(columns={"impactados": "Impactados", "activos": "Activos", "finalizados": "Finalizados",
                              "desertores": "Desertores", "matricula_no_exitosa": "Matrícula no exitosa"})

    variacion(tot, ["Impactados", "Activos", "Retención %", "Deserción %", "Aprobación %"],
              {"Retención %", "Deserción %", "Aprobación %"})

    col_a, col_b = st.columns(2)
    with col_a:
        elegidos = st.multiselect("Personas", ["Impactados", "Activos", "Finalizados", "Desertores",
                                               "Matrícula no exitosa"], default=["Impactados", "Activos", "Finalizados"],
                                  key="efe_ten_stock")
        if elegidos:
            largo = tot.melt(id_vars=["Etiqueta", "Origen"], value_vars=elegidos, var_name="Indicador", value_name="Personas")
            fig = px.line(largo, x="Etiqueta", y="Personas", color="Indicador", markers=True, title="Personas por estado (corte)",
                          color_discrete_sequence=PALETA)
            st.plotly_chart(dark(eje_periodo(fig), 360), use_container_width=True)
    with col_b:
        largo = tot.melt(id_vars=["Etiqueta"], value_vars=["Retención %", "Deserción %", "Aprobación %"],
                         var_name="Indicador", value_name="%")
        fig = px.line(largo, x="Etiqueta", y="%", color="Indicador", markers=True, title="Tasas (corte)",
                      color_discrete_map={"Retención %": VERDE, "Deserción %": ROJO, "Aprobación %": AZUL})
        fig.update_yaxes(range=[0, 105])
        st.plotly_chart(dark(eje_periodo(fig), 360), use_container_width=True)
    if (tot["Origen"] == "mensual").any() and (tot["Origen"] == "diaria").any():
        st.caption("Antes de la foto diaria solo hay un corte por mes (foto mensual); por eso, en Día o "
                   "Semana, los periodos anteriores aparecen espaciados.")

# ---------------------------------------------------------------------------- 2. nuevos (flujo)
st.subheader("Nuevos impactados por fecha de ingreso")
n = seg[seg["impactado"] & seg["fecha_ingreso"].notna()]
if proyecto != TODOS:
    n = n[n["Proyecto"] == proyecto]
    if programa != TODOS:
        n = n[n["Programa"] == programa]
n = en_rango(n, "fecha_ingreso")
if n.empty:
    st.info("Sin ingresos en este rango.")
else:
    n = n.assign(Periodo=m.periodo(n["fecha_ingreso"], gran))
    nuevos = n.groupby(["Periodo", "Proyecto"])["Documento"].nunique().rename("Nuevos").reset_index().sort_values("Periodo")
    nuevos["Etiqueta"] = etiqueta(nuevos["Periodo"])
    fig = px.bar(nuevos, x="Etiqueta", y="Nuevos", color="Proyecto", text="Nuevos", color_discrete_sequence=PALETA,
                 title=f"Nuevos por {gran.lower()} · total {m.fmt_num(nuevos['Nuevos'].sum())}")
    st.plotly_chart(dark(eje_periodo(fig), 340), use_container_width=True)
    st.caption("Fecha de ingreso a la formación según Unificado_Seguimiento (estado actual), por eso tiene historia completa.")

# ---------------------------------------------------------------------------- 3. satisfacción (flujo)
st.subheader("Satisfacción por fecha de encuesta")
s = sat.dropna(subset=["fecha"])
if proyecto != TODOS:
    s = s[s["Proyecto"] == proyecto]
s = en_rango(s, "fecha")
if s.empty:
    st.info("Sin encuestas de satisfacción en este rango.")
else:
    s = s.assign(Periodo=m.periodo(s["fecha"], gran))
    ss = (s.groupby("Periodo").agg(Encuestas=("NPS", "size"), NPS=("NPS", m.nps),
                                   Satisfacción=("Promedio_Satisfaccion", "mean")).reset_index().sort_values("Periodo"))
    ss["Etiqueta"] = etiqueta(ss["Periodo"])
    ss["NPS"] = ss["NPS"].round(1)
    ss["Satisfacción"] = ss["Satisfacción"].round(2)
    col_a, col_b = st.columns(2)
    with col_a:
        fig = px.line(ss, x="Etiqueta", y="NPS", markers=True, text="NPS", hover_data=["Encuestas"],
                      title="NPS (% promotores − % detractores)", color_discrete_sequence=[NARANJA])
        fig.update_traces(textposition="top center")
        nps_min = ss["NPS"].min()
        fig.update_yaxes(range=[-10 if pd.isna(nps_min) else min(-10, nps_min - 10), 105])
        st.plotly_chart(dark(eje_periodo(fig), 340), use_container_width=True)
    with col_b:
        fig = px.line(ss, x="Etiqueta", y="Satisfacción", markers=True, text="Satisfacción", hover_data=["Encuestas"],
                      title="Satisfacción general (1–5)", color_discrete_sequence=[VERDE])
        fig.add_hline(y=m.META_SATISFACCION, line_dash="dot", line_color=AMARILLO, annotation_text="Meta 4,5")
        fig.update_traces(textposition="top center")
        fig.update_yaxes(range=[1, 5.3])
        st.plotly_chart(dark(eje_periodo(fig), 340), use_container_width=True)
    st.caption(f"{m.fmt_num(ss['Encuestas'].sum())} encuestas en el rango (pasa el cursor para ver cuántas por periodo).")

# ---------------------------------------------------------------------------- 4. empleabilidad (stock)
st.subheader("Empleabilidad")
e = serie_emp.copy()
if proyecto != TODOS:
    e = e[e["Proyecto"] == proyecto]
e = en_rango(e, "Fecha")
if e.empty:
    st.info("Sin fotos de empleabilidad para este proyecto / rango (solo Suba, Ecolombia y Jóvenes a la E).")
else:
    et = e.groupby("Fecha", as_index=False)[["participantes", "contratados", "postulados", "postulaciones"]].sum()
    et = m.corte_por_periodo(et, gran, claves=[]).sort_values("Periodo")
    et["Colocación %"] = (100 * et["contratados"] / et["participantes"]).where(et["participantes"] > 0).round(1)
    et["Etiqueta"] = etiqueta(et["Periodo"])
    et = et.rename(columns={"participantes": "Participantes", "contratados": "Contratados", "postulados": "Postulados",
                            "postulaciones": "Postulaciones"})
    variacion(et, ["Participantes", "Postulados", "Contratados", "Colocación %"], {"Colocación %"})
    largo = et.melt(id_vars=["Etiqueta"], value_vars=["Participantes", "Postulados", "Contratados"],
                    var_name="Indicador", value_name="Personas")
    fig = px.line(largo, x="Etiqueta", y="Personas", color="Indicador", markers=True, title="Empleabilidad (corte)",
                  color_discrete_map={"Participantes": GRIS, "Postulados": AMARILLO, "Contratados": VERDE})
    st.plotly_chart(dark(eje_periodo(fig), 340), use_container_width=True)

# ---------------------------------------------------------------------------- 5. caracterización (flujo)
st.subheader("Caracterizaciones por fecha de encuesta")
c = car.dropna(subset=["fecha"])
if proyecto != TODOS:
    c = c[c["Proyecto"] == proyecto]
c = en_rango(c, "fecha")
if c.empty:
    st.info("Sin caracterizaciones con fecha en este rango.")
else:
    c = c.assign(Periodo=m.periodo(c["fecha"], gran))
    cc = c.groupby(["Periodo", "Proyecto"])["Documento"].nunique().rename("Caracterizados").reset_index().sort_values("Periodo")
    cc["Etiqueta"] = etiqueta(cc["Periodo"])
    fig = px.bar(cc, x="Etiqueta", y="Caracterizados", color="Proyecto", color_discrete_sequence=PALETA,
                 title=f"Caracterizados por {gran.lower()}")
    st.plotly_chart(dark(eje_periodo(fig), 320), use_container_width=True)
