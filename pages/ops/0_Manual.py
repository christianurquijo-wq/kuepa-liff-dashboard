"""
Manual de automatizaciones (oct-2026).

Página de consulta para cualquier persona que entre al dashboard: busca por
proyecto, palabra o estado, lee para qué sirve cada automatización, de dónde
lee y dónde escribe, qué hacer si falla, y ve cuáles requieren atención.

- Ver: público (no pide login).
- Ejecutar: login con Google + correo autorizado, con las mismas reglas del
  Panel (PIN en las sensibles). El botón es utils/ops_ui.py::boton_ejecutar.

Fuente: el CATALOGO del Sheet de operaciones. Los textos de cada ficha son las
columnas para_que_sirve, cuando_usarla, entrada, salida y si_falla; se editan en
el Sheet (scripts/ops_manual_catalogo.py crea las columnas y el borrador).
Lógica sin Streamlit en utils/ops_manual.py.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from utils.ops_auth import es_admin, sesion_opcional
from utils.ops_data import TZ, leer_catalogo, leer_log, refrescar
from utils.ops_manual import (GUIA_ERRORES, ORDEN_SEMAFORO, SEMAFORO, buscar, diagrama_dot, estados,
                              normalizar, partes)
from utils.ops_metrics import preparar
from utils.ops_ui import boton_ejecutar
from utils.ui import AZUL, GRIS, NARANJA, ROJO, VERDE, inject_css, kpi_row

inject_css()
correo, autorizado = sesion_opcional()
admin = bool(correo) and es_admin(correo)

col_t, col_b = st.columns([5, 1], vertical_alignment="center")
col_t.title("📘 Manual de automatizaciones")
if col_b.button("↻ Actualizar", use_container_width=True):
    refrescar()
    st.rerun()
st.caption("Qué hace cada automatización, cuándo usarla, de dónde lee y dónde escribe, y qué hacer si falla. "
           "Busca por proyecto, por palabra o por estado.")

try:
    catalogo = normalizar(leer_catalogo())
    log = preparar(leer_log(), catalogo)
except Exception as exc:  # noqa: BLE001 -- sin Sheet no hay manual, pero no se cae la app
    st.error(f"No se pudo leer el catálogo de automatizaciones: {exc}")
    st.stop()
if catalogo.empty:
    st.info("El catálogo está vacío.")
    st.stop()

ahora = pd.Timestamp(datetime.now(TZ))
datos = estados(catalogo, log, ahora)

# ------------------------------------------------------------------ sesión
if not correo:
    c1, c2 = st.columns([4, 1.3], vertical_alignment="center")
    c1.info("Puedes consultar todo el manual. Para **ejecutar** una automatización, inicia sesión con tu "
            "cuenta de Google de Kuepa.")
    if "auth" in st.secrets:
        c2.button("Iniciar sesión con Google", type="primary", on_click=st.login, use_container_width=True)
elif not autorizado:
    st.warning(f"Sesión: {correo}. Puedes consultar el manual, pero tu cuenta no está autorizada para "
               "ejecutar. Pide acceso a Christian.")
else:
    with st.sidebar:
        st.caption(f"Sesión: {correo}")
        st.button("Cerrar sesión", on_click=st.logout, key="man_logout")

if st.session_state.get("ops_solicitudes"):
    n = len(st.session_state["ops_solicitudes"])
    c1, c2 = st.columns([4, 1.3], vertical_alignment="center")
    c1.success(f"Enviaste {n} ejecución(es) en esta sesión. Sigue su avance en vivo en el Panel de control.")
    c2.page_link("pages/ops/1_Panel.py", label="Ir al Panel", icon="🎛️", use_container_width=True)

# ------------------------------------------------------------------ KPIs
activas = datos[datos["activo"]]
kpi_row([
    ("Automatizaciones", f"{len(activas)}", NARANJA, f"activas · {len(datos) - len(activas)} pendientes de habilitar"),
    ("Requieren atención", f"{int(datos['semaforo'].eq('REQUIERE').sum())}", ROJO, "fallaron o están atrasadas"),
    ("Al día", f"{int(datos['semaforo'].eq('AL_DIA').sum())}", VERDE, "corrieron bien a tiempo"),
    ("Manuales", f"{int(datos['semaforo'].eq('MANUAL').sum())}", AZUL, "se ejecutan cuando se necesitan"),
    ("Fichas por completar", f"{int((~datos['ficha_completa']).sum())}", GRIS, "sin 'para qué sirve' o 'cuándo usarla'"),
])
st.write("")

# ------------------------------------------------------------------ filtros
f1, f2, f3 = st.columns([2.2, 1.6, 1.6])
texto = f1.text_input("Buscar", placeholder="ej. satisfacción, JAE, BigQuery, certificados…")
proyectos = f2.multiselect("Proyecto", list(dict.fromkeys(datos["proyecto"])), placeholder="Todos")
opciones_sem = {k: f"{SEMAFORO[k][0]} {SEMAFORO[k][1]}" for k in ORDEN_SEMAFORO}
sems = f3.multiselect("Estado", list(opciones_sem), format_func=opciones_sem.get, placeholder="Todos")

vista = buscar(datos, texto)
if proyectos:
    vista = vista[vista["proyecto"].isin(proyectos)]
if sems:
    vista = vista[vista["semaforo"].isin(sems)]
vista = vista.assign(_orden=vista["semaforo"].map({k: i for i, k in enumerate(ORDEN_SEMAFORO)}))


def _lista(texto_campo: str) -> str:
    elementos = partes(texto_campo)
    return "\n".join(f"- {p}" for p in elementos) if elementos else "_Sin dato_"


def ficha(r: pd.Series) -> None:
    icono, etiqueta = SEMAFORO[r["semaforo"]]
    candado = " · 🔒" if r["sensible"] else ""
    with st.expander(f"{icono} **{r['nombre']}** — {etiqueta}{candado}"):
        izq, der = st.columns([3, 1.4], gap="large")
        with izq:
            if r["ficha_completa"]:
                st.markdown(f"**Para qué sirve**  \n{r['para_que_sirve']}")
                st.markdown(f"**Cuándo usarla**  \n{r['cuando_usarla']}")
            else:
                st.caption("📝 Ficha por completar en la hoja CATALOGO (columnas para_que_sirve y cuando_usarla).")
                if r["descripcion"]:
                    st.markdown(r["descripcion"])
            a, b = st.columns(2)
            a.markdown(f"**Lee de**\n{_lista(r['entrada'])}")
            b.markdown(f"**Entrega en**\n{_lista(r['salida'])}")
            if r["si_falla"]:
                st.markdown(f"**Si falla**  \n{r['si_falla']}")
        with der:
            with st.container(border=True):
                st.markdown(f"{icono} **{etiqueta}**")
                st.caption(r["motivo"])
                if pd.notna(r["ultima_fecha"]):
                    dur = r["ultima_duracion_seg"]
                    dur_txt = f" · {dur / 60:.1f} min" if pd.notna(dur) and dur else ""
                    st.caption(f"Última: {r['ultima_fecha']:%d-%b %H:%M} · {r['ultimo_estado']}{dur_txt}")
                    if r["ultimo_run_url"]:
                        st.markdown(f"[Ver ejecución]({r['ultimo_run_url']})")
                plataforma = "n8n" if r["plataforma"] == "n8n" else "GitHub Actions"
                st.caption(f"⏱ {r['frecuencia'] or 'Manual'} · {plataforma}"
                           + (f" · Responsable: {r['responsable']}" if r["responsable"] else ""))
            if not r["activo"]:
                st.caption("Sin botón hasta que se habilite (activo = NO en el CATALOGO).")
            elif autorizado:
                boton_ejecutar(r.to_dict(), correo, admin, prefijo="man_")
            elif correo:
                st.caption("Tu cuenta no está autorizada para ejecutar.")
            else:
                st.caption("🔐 Inicia sesión arriba para ejecutar.")
        if r["semaforo"] == "REQUIERE" and r["ultimo_error"]:
            st.markdown("**Último error registrado**")
            st.code(str(r["ultimo_error"])[:600], language="text")


tab_fichas, tab_flujo, tab_fallas, tab_ayuda = st.tabs(
    ["📋 Fichas", "🗺️ Flujo por proyecto", "🛠️ Si algo falla", "❓ Cómo usar este manual"])

with tab_fichas:
    if vista.empty:
        st.info("No hay automatizaciones que coincidan con la búsqueda.")
    for proyecto in dict.fromkeys(vista["proyecto"]):
        grupo = vista[vista["proyecto"].eq(proyecto)].sort_values(["_orden", "nombre"])
        atencion = int(grupo["semaforo"].eq("REQUIERE").sum())
        st.subheader(f"{proyecto}  ·  {len(grupo)}" + (f"  ·  🔴 {atencion}" if atencion else ""))
        for _, fila in grupo.iterrows():
            ficha(fila)

with tab_flujo:
    st.caption("Cómo se conectan las fuentes (Sheets, Drive), las automatizaciones y los destinos "
               "(BigQuery, tableros, correos). El borde de cada automatización indica su estado: "
               "🔴 requiere atención · 🟠 sin datos · 🟢 al día · 🔵 manual · ⚪ pendiente.")
    opciones = list(dict.fromkeys(vista["proyecto"]))
    if not opciones:
        st.info("No hay automatizaciones que coincidan con los filtros.")
    else:
        proyecto = st.selectbox("Proyecto", opciones, key="man_flujo_proyecto")
        sub = vista[vista["proyecto"].eq(proyecto)]
        if sub[["entrada", "salida"]].eq("").all(axis=None):
            st.info("Este proyecto aún no tiene completadas las columnas entrada / salida en el CATALOGO.")
        else:
            st.graphviz_chart(diagrama_dot(sub), use_container_width=True)

with tab_fallas:
    st.caption("Errores conocidos y qué hacer. Si el tuyo no está aquí, revisa el mensaje completo en "
               "Operaciones → Análisis de ejecuciones → Fallos recientes.")
    q = st.text_input("Buscar en la guía", placeholder="ej. 401, columnas, token, n8n…", key="man_guia_q")
    guia = [g for g in GUIA_ERRORES if not q.strip()
            or q.strip().lower() in " ".join(g.values()).lower()]
    if not guia:
        st.info("No hay coincidencias en la guía.")
    for g in guia:
        with st.expander(f"⚠️ {g['sintoma']}"):
            st.markdown(f"**Dónde aparece:** {g['donde']}  \n**Causa probable:** {g['causa']}  \n"
                        f"**Qué hacer:** {g['accion']}")
    st.page_link("pages/ops/2_Analisis.py", label="Ver fallos recientes en Análisis de ejecuciones", icon="📈")

with tab_ayuda:
    st.markdown(
        """
**1. Encuentra la automatización.** Escribe una palabra (proyecto, tema, nombre del Sheet o tabla)
o filtra por proyecto y estado. Cada ficha explica para qué sirve, cuándo usarla, qué lee y dónde
deja el resultado.

**2. Revisa el estado.**
- 🔴 **Requiere atención**: la última ejecución falló o lleva más tiempo del esperado sin correr.
- 🟠 **Sin datos**: debería correr sola, pero aún no hay ejecuciones registradas.
- 🟢 **Al día**: corrió bien dentro de su frecuencia.
- 🔵 **Manual**: no tiene horario; se ejecuta cuando se necesita.
- ⚪ **Pendiente de habilitar**: existe, pero falta corregir algo antes de darle botón.

**3. Ejecuta (requiere sesión).** Inicia sesión con tu cuenta de Google de Kuepa. Las marcadas con 🔒
piden PIN porque cambian datos sensibles o envían correos. Después de ejecutar, el avance se ve en
el Panel de control.

**¿Un texto está desactualizado?** Las fichas se editan en el Google Sheet de operaciones, hoja
**CATALOGO**, columnas *para_que_sirve, cuando_usarla, entrada, salida* y *si_falla*. En *entrada* y
*salida* separa cada elemento con «;» y empieza con su tipo (Sheet:, BigQuery:, Drive:, Correo:,
Dashboard:) para que aparezca bien en el diagrama. Los cambios se ven en máximo 5 minutos o con ↻ Actualizar.
"""
    )
