"""
IQ / Tipos de recurso (oct-2026) -- versión interactiva del análisis de la
reunión INICIA/MINERD del 22/10/2026 (sección "04 Tipos de recurso" del PPTX).

Qué responde (de arriba a abajo):
1. Filtros en la barra lateral: Periodo (ago–jul), Programa, Tipo de recurso,
   Rol y, en "Más filtros", Grado / Regional / Área. Todos se combinan.
   "Periodo principal" y "Comparar contra" fijan la comparativa de los KPI.
2. KPI de cabecera: consumos, usuarios únicos, consumos por usuario,
   finalización y puntaje del periodo principal vs el de comparación.
3. Pestañas: Resumen · Tipos de recurso · Grado y programa · Regional ·
   Estacionalidad (mes a mes del año académico) · Roles y áreas · Método.

Fuente: CSV agregados del repo (data/iq/tipos_recursos/agregados/), sin datos
personales y sin costo de infraestructura. Se regeneran con
scripts/build_tipos_recurso.py. Definiciones y límites en utils/iq_tipos_recurso.py
y en la pestaña "Método".
"""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.iq_tipos_recurso import (
    COLOR_PROG,
    COLOR_TIPO,
    MES_ORDEN,
    SIN_CENTRO,
    TIPOS_INTENTO,
    delta_html,
    filtrar,
    fmt_dec,
    fmt_int,
    fmt_pct,
    fmt_pts,
    grados_en_orden,
    load_conciliacion,
    load_cubo,
    load_unicos,
    periodos_info,
    resumen,
    tipos_en_orden,
    totales_periodo,
    usuarios_unicos,
    var_pct,
)
from utils.ui import AMARILLO, AZUL, GRIS, NARANJA, ROJO, VERDE, badge, dark, inject_css, kpi_row

inject_css()

st.markdown(badge("IQ · Tipos de recurso", "#29B6F6"), unsafe_allow_html=True)
st.title("Tipos de recurso")

cubo = load_cubo()
unicos = load_unicos()
if cubo.empty:
    st.error(
        "No encontré `data/iq/tipos_recursos/agregados/recursos_cubo.csv`. "
        "Genera los agregados con `python scripts/build_tipos_recurso.py` y haz commit de esa carpeta."
    )
    st.stop()

info = periodos_info(cubo)
periodos_all = list(info["periodo"])
incompletos = {r.periodo: int(r.meses) for r in info.itertuples() if not r.completo}
ultimo = cubo.loc[cubo["periodo"] == periodos_all[-1], ["anio", "mes"]].sort_values(["anio", "mes"]).iloc[-1]
st.caption(
    f"Fuente: exportes BigQuery de recursos de IQ Primaria y Secundaria (base depurada) · último mes con datos: "
    f"{int(ultimo['mes']):02d}/{int(ultimo['anio'])}. Periodo académico = agosto a julio. "
    "Definiciones y límites en la pestaña **Método**."
)


def lab(p: str) -> str:
    return f"{p} (parcial)" if p in incompletos else p


# ============================================================ filtros ======
def _opciones(col: str) -> list[str]:
    return sorted(cubo[col].astype(str).unique())


tipos_all = tipos_en_orden(_opciones("tipo"))
grados_all = grados_en_orden(_opciones("grado"))
regiones_all = _opciones("region")
areas_all = _opciones("area")
roles_all = _opciones("rol")
progs_all = _opciones("prog")

sb = st.sidebar
sb.header("Filtros -- Tipos de recurso")
default_periodos = [p for p in ("2024-25", "2025-26") if p in periodos_all] or periodos_all[-2:]
periodos_sel = sb.multiselect("Periodo académico (ago–jul)", periodos_all, default=default_periodos, format_func=lab, key="tr_periodos")
progs_sel = sb.multiselect("Programa", progs_all, default=progs_all, key="tr_progs")
tipos_sel = sb.multiselect("Tipo de recurso", tipos_all, default=tipos_all, key="tr_tipos")
roles_sel = sb.multiselect("Rol", roles_all, default=roles_all, key="tr_roles")
with sb.expander("Más filtros (grado, regional, área)"):
    grados_sel = st.multiselect("Grado", grados_all, default=grados_all, key="tr_grados")
    regiones_sel = st.multiselect("Regional educativa", regiones_all, default=regiones_all, key="tr_regiones")
    areas_sel = st.multiselect("Área de conocimiento", areas_all, default=areas_all, key="tr_areas")

if sb.button("↺ Restablecer filtros", key="tr_reset"):
    for k in ("tr_periodos", "tr_progs", "tr_tipos", "tr_roles", "tr_grados", "tr_regiones", "tr_areas", "tr_p1", "tr_p0"):
        st.session_state.pop(k, None)
    st.rerun()

faltan = [n for n, v in [("periodo", periodos_sel), ("programa", progs_sel), ("tipo de recurso", tipos_sel), ("rol", roles_sel),
                         ("grado", grados_sel), ("regional", regiones_sel), ("área", areas_sel)] if not v]
if faltan:
    st.warning("Selecciona al menos un valor en: " + ", ".join(faltan) + ".")
    st.stop()

periodos_sel = sorted(periodos_sel)
p1 = sb.selectbox("Periodo principal", periodos_sel, index=len(periodos_sel) - 1, format_func=lab, key="tr_p1")
otros_p = [p for p in periodos_sel if p < p1]
p0 = None
if otros_p:
    p0 = sb.selectbox("Comparar contra", otros_p, index=len(otros_p) - 1, format_func=lab, key="tr_p0")

f = filtrar(cubo, periodos_sel, progs_sel, tipos_sel, grados_sel, regiones_sel, areas_sel, roles_sel)
if f.empty or f["consumos"].sum() == 0:
    st.info("No hay consumos para esta combinación de filtros.")
    st.stop()

avisos = []
parciales_sel = [p for p in periodos_sel if p in incompletos]
if parciales_sel:
    avisos.append(
        "Periodos incompletos en la selección: "
        + ", ".join(f"{p} ({incompletos[p]} meses con datos)" for p in parciales_sel)
        + " -- no son comparables con un año académico completo."
    )
if any(p < "2022-23" for p in periodos_sel):
    avisos.append("Los periodos anteriores a 2022-23 tienen volúmenes muy bajos (sobre todo IQ Primaria): léelos como referencia, no como tendencia.")
for a in avisos:
    st.warning(a, icon="⚠️")

res_pt = resumen(f, ["periodo", "tipo"])  # periodo x tipo
res_p = resumen(f, ["periodo"])


def tabla_descarga(df: pd.DataFrame, nombre: str, key: str) -> None:
    st.download_button(
        "⬇ Descargar CSV", df.to_csv(index=False).encode("utf-8-sig"), file_name=f"{nombre}.csv", mime="text/csv", key=key,
    )


# ============================================================== KPIs =======
universo = {"tipo": tipos_all, "grado": grados_all, "area": areas_all, "rol": roles_all, "region": regiones_all}
seleccion = {"tipo": tipos_sel, "grado": grados_sel, "area": areas_sel, "rol": roles_sel, "region": regiones_sel}
t1 = totales_periodo(f, p1)
t0 = totales_periodo(f, p0) if p0 else None
u1 = usuarios_unicos(unicos, p1, progs_sel, seleccion, universo)
u0 = usuarios_unicos(unicos, p0, progs_sel, seleccion, universo) if p0 else None


def d_var(nuevo, viejo):
    v = var_pct(nuevo, viejo)
    if pd.isna(v):
        return ""
    return delta_html(f"{fmt_pct(v, 1, True)} vs {p0}", v >= 0) if p0 else ""


def d_pts(nuevo, viejo):
    if viejo is None or pd.isna(nuevo) or pd.isna(viejo):
        return ""
    return delta_html(f"{fmt_pts(nuevo - viejo)} vs {p0}", (nuevo - viejo) >= 0)


tarjetas = [("Consumos " + p1, fmt_int(t1["consumos"]), NARANJA, d_var(t1["consumos"], t0["consumos"]) if t0 else "Un solo periodo seleccionado")]
if u1 is not None:
    tarjetas.append(("Usuarios únicos", fmt_int(u1), AZUL, d_var(u1, u0) if u0 is not None else ""))
    prof1 = t1["consumos"] / u1 if u1 else np.nan
    prof0 = (t0["consumos"] / u0) if (t0 and u0) else np.nan
    tarjetas.append(("Consumos por usuario", fmt_dec(prof1, 1), VERDE, d_var(prof1, prof0) if p0 else ""))
else:
    ayuda = "Disponible con todos los valores o un solo valor por filtro (regional solo junto a tipo)"
    tarjetas.append(("Usuarios únicos", "—", GRIS, ayuda))
    tarjetas.append(("Consumos por usuario", "—", GRIS, "Requiere usuarios únicos"))
if not np.isnan(t1["finalizacion"]):
    tarjetas.append(("Finalización", fmt_pct(t1["finalizacion"]), VERDE, d_pts(t1["finalizacion"], t0["finalizacion"]) if t0 else "Diagnóstico, simulacro y ejercitación"))
    tarjetas.append(("Puntaje medio", fmt_dec(t1["puntaje"], 1), AMARILLO, d_pts(t1["puntaje"], t0["puntaje"]) if t0 else "Intentos terminados, 0–100"))
else:
    tarjetas.append(("Finalización", "—", GRIS, "No aplica a video / editor / juego / otros"))
    tarjetas.append(("Puntaje medio", "—", GRIS, "No aplica a video / editor / juego / otros"))
kpi_row(tarjetas)
if len(progs_sel) > 1 and u1 is not None:
    st.caption("Usuarios únicos con IQP + IQS: suma de ambos programas (casi no comparten usuarios). No es comparable con los usuarios-mes de otras páginas.")
st.write("")

tabs = st.tabs(["📊 Resumen", "🧩 Tipos de recurso", "🎓 Grado y programa", "🗺️ Regional", "📅 Estacionalidad", "👥 Roles y áreas", "ℹ️ Método"])
t_res, t_tipo, t_grado, t_reg, t_est, t_rol, t_met = tabs

CAT_TIPO = {"tipo": tipos_all}
LEYENDA_H = dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)


def con_leyenda(fig, facet: bool = False, **kw):
    fig = dark(fig, kw.pop("height", 340))
    leyenda = dict(LEYENDA_H, y=1.17) if facet else LEYENDA_H  # con facetas, deja sitio a los títulos de cada panel
    fig.update_layout(legend=leyenda, title=dict(x=0, y=0.98, yanchor="top"), margin=dict(t=135 if facet else 95, b=10, l=10, r=10), **kw)
    return fig


# ----------------------------------------------------------- Resumen -------
with t_res:
    c1, c2 = st.columns([2, 3])
    with c1:
        fig = px.bar(res_pt, x="periodo", y="consumos", color="tipo", color_discrete_map=COLOR_TIPO, category_orders=CAT_TIPO,
                     title="Consumos por periodo y tipo")
        fig.update_layout(xaxis_title="", yaxis_title="Consumos")
        st.plotly_chart(con_leyenda(fig, height=380), width="stretch", key="tr_res_stack")
    with c2:
        if p0:
            a = res_pt[res_pt["periodo"] == p0].set_index("tipo")
            b = res_pt[res_pt["periodo"] == p1].set_index("tipo")
            tt = [t for t in tipos_all if t in a.index or t in b.index]
            tb = pd.DataFrame(index=tt)
            tb["c0"] = a["consumos"].reindex(tt).fillna(0)
            tb["c1"] = b["consumos"].reindex(tt).fillna(0)
            tb["d"] = tb["c1"] - tb["c0"]
            tb["dp"] = [var_pct(x, y) for x, y in zip(tb["c1"], tb["c0"])]
            tb["s0"] = tb["c0"] / tb["c0"].sum() * 100
            tb["s1"] = tb["c1"] / tb["c1"].sum() * 100
            tb["f1"] = b["finalizacion"].reindex(tt)
            tb["p1"] = b["puntaje"].reindex(tt)
            tb = tb.sort_values("c1", ascending=False)
            vista = pd.DataFrame({
                "Tipo": tb.index,
                p0: [fmt_int(x) for x in tb["c0"]],
                p1: [fmt_int(x) for x in tb["c1"]],
                "Δ": [("+" if x > 0 else "") + fmt_int(x) for x in tb["d"]],
                "Δ %": [fmt_pct(x, 1, True) for x in tb["dp"]],
                f"Part. {p0}": [fmt_pct(x) for x in tb["s0"]],
                f"Part. {p1}": [fmt_pct(x) for x in tb["s1"]],
                "Δ part.": [fmt_pts(y - x) for x, y in zip(tb["s0"], tb["s1"])],
                f"Finaliz. {p1}": [fmt_pct(x) for x in tb["f1"]],
                f"Puntaje {p1}": [fmt_dec(x) for x in tb["p1"]],
            })
            st.markdown(f"**Comparativa por tipo: {p1} vs {p0}**")
            st.dataframe(vista, hide_index=True, width="stretch")
            tabla_descarga(vista, "comparativa_tipos", "tr_dl_comp")
        else:
            st.info("Selecciona dos o más periodos para ver la comparativa por tipo.")

    if p0:
        st.markdown("**Lectura rápida**")
        l = []
        tot_v = var_pct(t1["consumos"], t0["consumos"])
        l.append(f"Los consumos {'subieron' if tot_v >= 0 else 'bajaron'} **{fmt_pct(abs(tot_v))}** ({fmt_int(t0['consumos'])} → {fmt_int(t1['consumos'])}) en {p1} frente a {p0}." if not pd.isna(tot_v) else "")
        sube = tb["d"].idxmax()
        baja = tb["d"].idxmin()
        if tb.loc[sube, "d"] > 0:
            l.append(f"Mayor crecimiento absoluto: **{sube}** ({'+' if tb.loc[sube, 'd'] > 0 else ''}{fmt_int(tb.loc[sube, 'd'])}, {fmt_pct(tb.loc[sube, 'dp'], 1, True)}).")
        if tb.loc[baja, "d"] < 0:
            l.append(f"Mayor caída absoluta: **{baja}** ({fmt_int(tb.loc[baja, 'd'])}, {fmt_pct(tb.loc[baja, 'dp'], 1, True)}).")
        lider = tb["s1"].idxmax()
        l.append(f"**{lider}** concentra {fmt_pct(tb.loc[lider, 's1'])} del consumo en {p1} ({fmt_pts(tb.loc[lider, 's1'] - tb.loc[lider, 's0'])} vs {p0}).")
        if not np.isnan(t1["finalizacion"]) and t0 and not np.isnan(t0["finalizacion"]):
            l.append(f"Finalización {fmt_pct(t1['finalizacion'])} ({fmt_pts(t1['finalizacion'] - t0['finalizacion'])}) y puntaje medio {fmt_dec(t1['puntaje'])} ({fmt_pts(t1['puntaje'] - t0['puntaje'])}).")
        st.markdown("\n".join(f"- {x}" for x in l if x))

# ------------------------------------------------------------- Tipos -------
with t_tipo:
    vista_t = st.radio("Vista", ["Consumos", "% del periodo"], horizontal=True, key="tr_tipo_vista")
    c1, c2 = st.columns(2)
    d = res_pt.copy()
    if vista_t == "% del periodo":
        d["valor"] = d["consumos"] / d.groupby("periodo", observed=True)["consumos"].transform("sum") * 100
        ytit, ttl = "% del periodo", "Mix de tipos de recurso (% del consumo del periodo)"
    else:
        d["valor"], ytit, ttl = d["consumos"], "Consumos", "Consumos por tipo de recurso"
    with c1:
        fig = px.bar(d, x="tipo", y="valor", color="periodo", barmode="group", category_orders=CAT_TIPO, title=ttl,
                     color_discrete_sequence=[GRIS, NARANJA, AZUL, VERDE, "#F5B942", "#A78BFA", "#F78FB3"])
        fig.update_layout(xaxis_title="", yaxis_title=ytit)
        st.plotly_chart(con_leyenda(fig), width="stretch", key="tr_tipo_mix")
    with c2:
        if p0:
            a = res_pt[res_pt["periodo"] == p0].set_index("tipo")["consumos"]
            b = res_pt[res_pt["periodo"] == p1].set_index("tipo")["consumos"]
            dv = pd.DataFrame({"c0": a, "c1": b}).fillna(0)
            dv["var"] = [var_pct(x, y) for x, y in zip(dv["c1"], dv["c0"])]
            dv = dv.reset_index().rename(columns={"index": "tipo"}).dropna(subset=["var"])
            dv["color"] = np.where(dv["var"] >= 0, "Sube", "Baja")
            dv["tipo"] = pd.Categorical(dv["tipo"], categories=tipos_all, ordered=True)
            dv = dv.sort_values("tipo")
            fig = px.bar(dv, x="tipo", y="var", color="color", color_discrete_map={"Sube": VERDE, "Baja": ROJO},
                         title=f"Variación de consumos por tipo ({p1} vs {p0}, %)", text=dv["var"].map(lambda x: fmt_pct(x, 0, True)))
            fig.update_layout(xaxis_title="", yaxis_title="Variación %", showlegend=False)
            st.plotly_chart(dark(fig, 340), width="stretch", key="tr_tipo_var")
        else:
            st.info("Elige dos periodos para ver la variación por tipo.")

    intentos = res_pt[res_pt["tipo"].isin(TIPOS_INTENTO) & (res_pt["grupos"] > 0)]
    if intentos.empty:
        st.caption("Finalización y puntaje solo aplican a diagnóstico, simulacro y ejercitación (no hay en la selección).")
    else:
        c3, c4 = st.columns(2)
        with c3:
            fig = px.bar(intentos, x="tipo", y="finalizacion", color="periodo", barmode="group", title="Finalización por tipo (%)",
                         category_orders={"tipo": TIPOS_INTENTO}, color_discrete_sequence=[GRIS, NARANJA, AZUL, VERDE, "#F5B942", "#A78BFA", "#F78FB3"],
                         text=intentos["finalizacion"].map(lambda x: fmt_dec(x, 0)))
            fig.update_layout(xaxis_title="", yaxis_title="% con intento terminado", yaxis_range=[0, 105])
            st.plotly_chart(con_leyenda(fig), width="stretch", key="tr_tipo_fin")
        with c4:
            fig = px.bar(intentos, x="tipo", y="puntaje", color="periodo", barmode="group", title="Puntaje medio por tipo (0–100)",
                         category_orders={"tipo": TIPOS_INTENTO}, color_discrete_sequence=[GRIS, NARANJA, AZUL, VERDE, "#F5B942", "#A78BFA", "#F78FB3"],
                         text=intentos["puntaje"].map(lambda x: fmt_dec(x, 1)))
            fig.update_layout(xaxis_title="", yaxis_title="Puntaje medio", yaxis_range=[0, 100])
            st.plotly_chart(con_leyenda(fig), width="stretch", key="tr_tipo_sc")
        st.caption("Finalización = % de grupos (usuario, componente, día) con al menos un intento terminado. Puntaje = promedio de intentos terminados con score.")
    with st.expander("Ver tabla completa por periodo y tipo"):
        tb_full = res_pt[["periodo", "tipo", "consumos", "grupos", "grupos_fin", "finalizacion", "n_con_puntaje", "puntaje"]].copy()
        tb_full["tipo"] = pd.Categorical(tb_full["tipo"], categories=tipos_all, ordered=True)
        tb_full = tb_full.sort_values(["periodo", "tipo"])
        st.dataframe(tb_full.round(1), hide_index=True, width="stretch")
        tabla_descarga(tb_full.round(2), "tipos_por_periodo", "tr_dl_tipo")

# ---------------------------------------------------- Grado y programa -----
with t_grado:
    st.markdown("#### Por grado")
    cg1, cg2 = st.columns([1, 1])
    p_hm = cg1.selectbox("Periodo a mostrar en el mapa de calor", periodos_sel, index=periodos_sel.index(p1), format_func=lab, key="tr_g_p")
    modo_hm = cg2.radio("Valores", ["% del grado", "Consumos"], horizontal=True, key="tr_g_modo")
    hm = f[f["periodo"] == p_hm].groupby(["grado", "tipo"], observed=True)["consumos"].sum().unstack("tipo").fillna(0)
    hm = hm.reindex([g for g in grados_all if g in hm.index])
    hm = hm[[t for t in tipos_all if t in hm.columns]]
    if modo_hm == "% del grado":
        z = hm.div(hm.sum(axis=1).replace(0, np.nan), axis=0) * 100
        txt = ".0f"
    else:
        z, txt = hm, ".3s"
    fig = px.imshow(z, text_auto=txt, aspect="auto", color_continuous_scale=[[0, "#1A1A1A"], [1, NARANJA]],
                    labels=dict(x="", y="Grado", color=""), title=f"Tipo de recurso por grado -- {p_hm}")
    st.plotly_chart(dark(fig, 360), width="stretch", key="tr_g_hm")

    gtp = resumen(f, ["periodo", "grado", "tipo"])
    gtp["grado"] = pd.Categorical(gtp["grado"], categories=grados_all, ordered=True)
    fig = px.bar(gtp, x="grado", y="consumos", color="tipo", facet_col="periodo", color_discrete_map=COLOR_TIPO,
                 category_orders={"tipo": tipos_all, "grado": grados_all}, title="Consumos por grado y tipo, por periodo")
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    fig.update_layout(xaxis_title="", yaxis_title="Consumos")
    st.plotly_chart(con_leyenda(fig, facet=True, height=420), width="stretch", key="tr_g_stack")

    gp = resumen(f, ["periodo", "grado"])
    if p0:
        a = gp[gp["periodo"] == p0].set_index("grado")
        b = gp[gp["periodo"] == p1].set_index("grado")
        gs = [g for g in grados_all if g in a.index or g in b.index]
        tg = pd.DataFrame({
            "Grado": gs,
            p0: [fmt_int(a["consumos"].get(g, 0)) for g in gs],
            p1: [fmt_int(b["consumos"].get(g, 0)) for g in gs],
            "Δ %": [fmt_pct(var_pct(b["consumos"].get(g, np.nan), a["consumos"].get(g, np.nan)), 1, True) for g in gs],
            f"Finaliz. {p0}": [fmt_pct(a["finalizacion"].get(g, np.nan)) for g in gs],
            f"Finaliz. {p1}": [fmt_pct(b["finalizacion"].get(g, np.nan)) for g in gs],
            f"Puntaje {p0}": [fmt_dec(a["puntaje"].get(g, np.nan)) for g in gs],
            f"Puntaje {p1}": [fmt_dec(b["puntaje"].get(g, np.nan)) for g in gs],
        })
        st.markdown(f"**Variación por grado: {p1} vs {p0}**")
        st.dataframe(tg, hide_index=True, width="stretch")
        tabla_descarga(tg, "variacion_por_grado", "tr_dl_grado")
        if "Sin dato" in gs:
            st.caption("«Sin dato»: registros cuyo grado no se pudo identificar (cuenta sin grupo/curso asignado).")

    st.markdown("#### Por programa (IQ Primaria vs IQ Secundaria)")
    modo_pg = st.radio("Vista", ["% del programa", "Consumos"], horizontal=True, key="tr_pg_modo")
    pgt = resumen(f, ["periodo", "prog", "tipo"])
    if modo_pg == "% del programa":
        pgt["valor"] = pgt["consumos"] / pgt.groupby(["periodo", "prog"], observed=True)["consumos"].transform("sum") * 100
        yt = "% del programa"
    else:
        pgt["valor"], yt = pgt["consumos"], "Consumos"
    fig = px.bar(pgt, x="periodo", y="valor", color="tipo", facet_col="prog", color_discrete_map=COLOR_TIPO,
                 category_orders={"tipo": tipos_all}, title="Mix de tipos por programa")
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    fig.update_layout(xaxis_title="", yaxis_title=yt)
    st.plotly_chart(con_leyenda(fig, facet=True, height=420), width="stretch", key="tr_pg_mix")
    pr = resumen(f, ["prog", "periodo"]).rename(columns={"prog": "Programa", "periodo": "Periodo"})
    pr_v = pr[["Programa", "Periodo", "consumos", "finalizacion", "puntaje"]].copy()
    pr_v.columns = ["Programa", "Periodo", "Consumos", "Finalización %", "Puntaje medio"]
    pr_v["Consumos"] = pr_v["Consumos"].map(fmt_int)
    pr_v["Finalización %"] = pr_v["Finalización %"].map(fmt_pct)
    pr_v["Puntaje medio"] = pr_v["Puntaje medio"].map(fmt_dec)
    st.dataframe(pr_v, hide_index=True, width="stretch")
    st.caption("IQ Primaria tiene un volumen mucho menor que Secundaria desde 2024-25: compara su mix con cautela.")

# --------------------------------------------------------------- Regional ---
with t_reg:
    cr1, cr2 = st.columns([1, 1])
    incl_sc = cr1.toggle("Incluir «Sin centro identificado»", value=False, key="tr_r_sc",
                         help="Registros cuyo usuario no tiene centro educativo asignado o eligió 'No encuentro mi centro'.")
    p_r = cr2.selectbox("Periodo a mostrar", periodos_sel, index=periodos_sel.index(p1), format_func=lab, key="tr_r_p")
    fr = f if incl_sc else f[f["region"] != SIN_CENTRO]
    tot_p = f[f["periodo"] == p_r]["consumos"].sum()
    sin_c = f[(f["periodo"] == p_r) & (f["region"] == SIN_CENTRO)]["consumos"].sum()
    if tot_p:
        st.caption(f"En {p_r}, {fmt_pct(sin_c / tot_p * 100)} de los consumos no tiene centro/regional identificado.")
    rr = resumen(fr, ["periodo", "region"])
    orden = rr[rr["periodo"] == p_r].sort_values("consumos", ascending=True)["region"].astype(str).tolist()
    rr["region"] = rr["region"].astype(str)
    fig = px.bar(rr, y="region", x="consumos", color="periodo", barmode="group", orientation="h",
                 category_orders={"region": orden}, title="Consumos por regional educativa",
                 color_discrete_sequence=[GRIS, NARANJA, AZUL, VERDE, "#F5B942", "#A78BFA", "#F78FB3"])
    fig.update_layout(yaxis_title="", xaxis_title="Consumos")
    st.plotly_chart(con_leyenda(fig, height=max(380, 24 * len(orden) + 120)), width="stretch", key="tr_r_bar")

    c1, c2 = st.columns(2)
    with c1:
        rt = resumen(fr[fr["periodo"] == p_r], ["region", "tipo"])
        rt["region"] = rt["region"].astype(str)
        rt["pct"] = rt["consumos"] / rt.groupby("region")["consumos"].transform("sum") * 100
        fig = px.bar(rt, y="region", x="pct", color="tipo", orientation="h", color_discrete_map=COLOR_TIPO,
                     category_orders={"region": orden, "tipo": tipos_all}, title=f"Mix de tipos por regional -- {p_r} (%)")
        fig.update_layout(yaxis_title="", xaxis_title="% de la regional")
        st.plotly_chart(con_leyenda(fig, height=max(380, 24 * len(orden) + 120)), width="stretch", key="tr_r_mix")
    with c2:
        if p0:
            a = rr[rr["periodo"] == p0].set_index("region")["consumos"]
            b = rr[rr["periodo"] == p1].set_index("region")["consumos"]
            dd = pd.DataFrame({"c0": a, "c1": b}).dropna()
            dd = dd[dd["c0"] >= 100]
            dd["var"] = [var_pct(y, x) for x, y in zip(dd["c0"], dd["c1"])]
            dd = dd.sort_values("var").reset_index().rename(columns={"index": "region"})
            dd["signo"] = np.where(dd["var"] >= 0, "Sube", "Baja")
            fig = px.bar(dd, y="region", x="var", orientation="h", color="signo", color_discrete_map={"Sube": VERDE, "Baja": ROJO},
                         title=f"Variación de consumos {p1} vs {p0} (%)", text=dd["var"].map(lambda x: fmt_pct(x, 0, True)))
            fig.update_layout(yaxis_title="", xaxis_title="Variación %", showlegend=False)
            st.plotly_chart(dark(fig, max(380, 24 * len(dd) + 120)), width="stretch", key="tr_r_var")
            st.caption("Solo regionales con al menos 100 consumos en el periodo de comparación.")
        else:
            st.info("Elige dos periodos para ver la variación por regional.")

    rgt = resumen(fr[fr["periodo"] == p_r], ["region"]).sort_values("consumos", ascending=False)
    rgt_v = pd.DataFrame({
        "Regional": rgt["region"].astype(str), "Consumos": rgt["consumos"].astype(int),
        "Part. %": (rgt["consumos"] / rgt["consumos"].sum() * 100).round(1),
        "Finalización %": rgt["finalizacion"].round(1), "Puntaje medio": rgt["puntaje"].round(1),
    })
    with st.expander(f"Ver tabla por regional -- {p_r}"):
        st.dataframe(rgt_v, hide_index=True, width="stretch")
        tabla_descarga(rgt_v, f"regional_{p_r}", "tr_dl_reg")

# ----------------------------------------------------------- Estacionalidad -
with t_est:
    me = resumen(f, ["periodo", "mes_label"])
    me["mes_label"] = me["mes_label"].astype(str)
    metrica = st.radio("Métrica", ["Consumos", "Finalización (%)", "Puntaje medio"], horizontal=True, key="tr_e_met")
    col_m, tit_m = {"Consumos": ("consumos", "Consumos por mes del año académico"),
                    "Finalización (%)": ("finalizacion", "Finalización por mes (%)"),
                    "Puntaje medio": ("puntaje", "Puntaje medio por mes")}[metrica]
    fig = px.line(me, x="mes_label", y=col_m, color="periodo", markers=True, category_orders={"mes_label": MES_ORDEN}, title=tit_m,
                  color_discrete_sequence=[GRIS, NARANJA, AZUL, VERDE, "#F5B942", "#A78BFA", "#F78FB3"])
    fig.update_layout(xaxis_title="Mes (agosto → julio)", yaxis_title=metrica)
    st.plotly_chart(con_leyenda(fig, height=360), width="stretch", key="tr_e_line")
    if metrica != "Consumos":
        st.caption("Meses con muy pocos intentos producen valores inestables; lee el patrón, no cada punto.")

    c1, c2 = st.columns(2)
    p_e = c1.selectbox("Periodo para el detalle por tipo", periodos_sel, index=periodos_sel.index(p1), format_func=lab, key="tr_e_p")
    modo_e = c2.radio("Valores", ["Consumos", "% del mes"], horizontal=True, key="tr_e_modo")
    met = resumen(f[f["periodo"] == p_e], ["mes_label", "tipo"])
    met["mes_label"] = met["mes_label"].astype(str)
    if modo_e == "% del mes":
        met["valor"] = met["consumos"] / met.groupby("mes_label")["consumos"].transform("sum") * 100
    else:
        met["valor"] = met["consumos"]
    fig = px.bar(met, x="mes_label", y="valor", color="tipo", color_discrete_map=COLOR_TIPO,
                 category_orders={"mes_label": MES_ORDEN, "tipo": tipos_all}, title=f"Mix de tipos por mes -- {p_e}")
    fig.update_layout(xaxis_title="Mes (agosto → julio)", yaxis_title=modo_e)
    st.plotly_chart(con_leyenda(fig, height=360), width="stretch", key="tr_e_stack")

    pv = me.pivot(index="mes_label", columns="periodo", values="consumos").reindex(MES_ORDEN)
    pico = {p: pv[p].idxmax() for p in pv.columns if pv[p].notna().any()}
    if pico:
        st.caption("Mes pico de consumo: " + " · ".join(f"**{p}**: {m}" for p, m in pico.items()))
    with st.expander("Ver tabla mensual"):
        pv_v = pv.reset_index().rename(columns={"mes_label": "Mes"})
        if p0 and p0 in pv.columns and p1 in pv.columns:
            pv_v["Δ %"] = [round(var_pct(y, x), 1) if pd.notna(var_pct(y, x)) else np.nan for x, y in zip(pv[p0], pv[p1])]
        st.dataframe(pv_v, hide_index=True, width="stretch")
        tabla_descarga(pv_v, "consumos_por_mes", "tr_dl_mes")

# ------------------------------------------------------------ Roles / áreas -
with t_rol:
    st.markdown("#### Por rol")
    rl = resumen(f, ["periodo", "rol"])
    rl["rol"] = rl["rol"].astype(str)
    sin_est = st.toggle("Ocultar «Estudiante» para ver los demás roles", value=False, key="tr_rol_sin")
    rl_p = rl[rl["rol"] != "Estudiante"] if sin_est else rl
    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(rl_p, x="rol", y="consumos", color="periodo", barmode="group", title="Consumos por rol",
                     color_discrete_sequence=[GRIS, NARANJA, AZUL, VERDE, "#F5B942", "#A78BFA", "#F78FB3"])
        fig.update_layout(xaxis_title="", yaxis_title="Consumos")
        st.plotly_chart(con_leyenda(fig), width="stretch", key="tr_rol_bar")
    with c2:
        rt = resumen(f[f["periodo"] == p1], ["rol", "tipo"])
        rt["rol"] = rt["rol"].astype(str)
        if sin_est:
            rt = rt[rt["rol"] != "Estudiante"]
        rt["pct"] = rt["consumos"] / rt.groupby("rol")["consumos"].transform("sum") * 100
        fig = px.bar(rt, x="rol", y="pct", color="tipo", color_discrete_map=COLOR_TIPO, category_orders={"tipo": tipos_all},
                     title=f"Mix de tipos por rol -- {p1} (%)")
        fig.update_layout(xaxis_title="", yaxis_title="% del rol")
        st.plotly_chart(con_leyenda(fig), width="stretch", key="tr_rol_mix")
    rl_v = rl[["periodo", "rol", "consumos", "finalizacion", "puntaje"]].copy()
    rl_v.columns = ["Periodo", "Rol", "Consumos", "Finalización %", "Puntaje medio"]
    with st.expander("Ver tabla por rol"):
        st.dataframe(rl_v.round(1), hide_index=True, width="stretch")
        tabla_descarga(rl_v.round(2), "consumos_por_rol", "tr_dl_rol")

    st.markdown("#### Por área de conocimiento")
    ar = resumen(f, ["periodo", "area"])
    ar["area"] = ar["area"].astype(str)
    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(ar, x="area", y="consumos", color="periodo", barmode="group", title="Consumos por área",
                     color_discrete_sequence=[GRIS, NARANJA, AZUL, VERDE, "#F5B942", "#A78BFA", "#F78FB3"])
        fig.update_layout(xaxis_title="", yaxis_title="Consumos")
        st.plotly_chart(con_leyenda(fig), width="stretch", key="tr_ar_bar")
    with c2:
        art = resumen(f[f["periodo"] == p1], ["area", "tipo"])
        art["area"] = art["area"].astype(str)
        art["pct"] = art["consumos"] / art.groupby("area")["consumos"].transform("sum") * 100
        fig = px.bar(art, x="area", y="pct", color="tipo", color_discrete_map=COLOR_TIPO, category_orders={"tipo": tipos_all},
                     title=f"Mix de tipos por área -- {p1} (%)")
        fig.update_layout(xaxis_title="", yaxis_title="% del área")
        st.plotly_chart(con_leyenda(fig), width="stretch", key="tr_ar_mix")
    sc_ar = resumen(f[f["tipo"].isin(["Simulacro", "Diagnóstico"])], ["periodo", "area", "tipo"])
    sc_ar = sc_ar[sc_ar["n_con_puntaje"] > 0]
    if not sc_ar.empty:
        sc_ar["area"] = sc_ar["area"].astype(str)
        fig = px.bar(sc_ar, x="area", y="puntaje", color="periodo", barmode="group", facet_col="tipo", title="Puntaje medio por área (simulacro y diagnóstico)",
                     color_discrete_sequence=[GRIS, NARANJA, AZUL, VERDE, "#F5B942", "#A78BFA", "#F78FB3"])
        fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
        fig.update_layout(xaxis_title="", yaxis_title="Puntaje medio", yaxis_range=[0, 100])
        st.plotly_chart(con_leyenda(fig, facet=True, height=400), width="stretch", key="tr_ar_sc")
        st.caption("El área de simulacros y diagnósticos se deriva del nombre del recurso (en el origen venía mal etiquetada).")

# ------------------------------------------------------------------ Método --
with t_met:
    st.markdown(
        """
**Qué es un «consumo».** Un intento único en diagnóstico, simulacro o ejercitación (las reaperturas del mismo intento no cuentan) o una vista de componente en video, editor, juego y otros.

**Base depurada.** Se excluyen las cuentas con más de 500 registros en un programa y periodo (cuentas atípicas o automáticas). La conciliación de abajo muestra cuánto se descarta por periodo.

**Periodo académico.** Del 1 de agosto al 31 de julio. Los periodos incompletos se marcan «parcial».

**Finalización.** % de grupos (usuario, componente, día) con al menos un intento terminado; solo diagnóstico, simulacro y ejercitación. **Puntaje medio.** Promedio de los intentos terminados con score (0–100).

**Usuarios únicos.** Se cuentan sobre usuarios distintos del periodo y **no se pueden sumar entre cortes** (un estudiante usa varios tipos). Por eso solo se muestran cuando cada filtro está en «todos» o en un único valor, y regional solo se combina con tipo. No son comparables con los «usuarios-mes» de las otras páginas de IQ.

**Calidad de datos.** El área de simulacros/diagnósticos se deriva del nombre del recurso; BAORUCO se unifica en BAHORUCO; «Sin centro identificado» agrupa registros sin centro o con «No encuentro mi centro». El tiempo de visualización (`time_view`) viene incompleto y no se usa en los indicadores.

**Actualización.** Los datos son una foto. Para refrescarlos: descargar los exportes, correr `python scripts/build_tipos_recurso.py` y hacer commit de `data/iq/tipos_recursos/agregados/`. Los xlsx crudos contienen nombres y correos y **no se suben al repo**.
        """
    )
    conc = load_conciliacion()
    if not conc.empty:
        st.markdown("**Conciliación de registros por programa y periodo**")
        cv = conc.rename(columns={
            "prog": "Programa", "periodo": "Periodo", "registros_brutos": "Registros brutos", "sin_revisiones": "Sin reaperturas",
            "base_depurada": "Base depurada", "usuarios_depurada": "Usuarios (base depurada)", "cuentas_atipicas": "Cuentas atípicas excluidas",
        })
        st.dataframe(cv, hide_index=True, width="stretch")
        tabla_descarga(cv, "conciliacion_tipos_recurso", "tr_dl_conc")
    st.markdown("**Descarga de la selección actual (cubo filtrado)**")
    tabla_descarga(f.drop(columns=["mes_label"]), "tipos_recurso_seleccion", "tr_dl_cubo")
