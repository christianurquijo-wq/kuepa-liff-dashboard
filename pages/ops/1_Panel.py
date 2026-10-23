"""
Operaciones -- Panel de control.

Un botón por automatización del CATALOGO (Google Sheet de operaciones).
GitHub Actions ejecuta los scripts de Python; n8n Cloud los flujos de n8n.
Cada ejecución queda en LOG_EJECUCIONES (la escribe ops_logger.py en cada
repo, o el flujo "OPS - Sync n8n") y cada clic en SOLICITUDES.

Acceso: login Google + lista de correos (utils/ops_auth.py). Los botones
marcados como sensibles piden PIN.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from utils.ops_auth import es_admin, requiere_login
from utils.ops_data import TZ, leer_catalogo, leer_log, refrescar
from utils.ops_dispatch import buscar_run, runs_recientes
from utils.ops_metrics import preparar, ultimo_lote
from utils.ops_n8n import estado_solicitud
from utils.ops_ui import boton_ejecutar
from utils.ui import AMARILLO, AZUL, GRIS, NARANJA, ROJO, VERDE, badge, inject_css, kpi_row

inject_css()
usuario = requiere_login()
admin = es_admin(usuario)

COLOR_ESTADO = {"EXITOSO": VERDE, "FALLIDO": ROJO, "TIMEOUT": AMARILLO, "EN CURSO": AZUL, "SIN DATOS": GRIS}
ICONO_ESTADO = {"EXITOSO": "✔", "FALLIDO": "✖", "TIMEOUT": "⏱", "EN CURSO": "⟳", "SIN DATOS": "–"}

col_t, col_b = st.columns([5, 1], vertical_alignment="center")
col_t.title("Panel de control")
if col_b.button("↻ Actualizar", use_container_width=True):
    refrescar()
    runs_recientes.clear()
    st.rerun()

catalogo = leer_catalogo()
if catalogo.empty:
    st.warning("El CATALOGO está vacío. Corre scripts/ops_setup_sheet.py (ver la guía).")
    st.stop()
log = preparar(leer_log(), catalogo)
ahora = pd.Timestamp(datetime.now(TZ))

# ------------------------------------------------------------------ KPIs
ult24 = log[log["fecha_inicio"] >= ahora - pd.Timedelta(hours=24)] if len(log) else log
repos_gh = sorted(catalogo.loc[catalogo["plataforma"].eq("github") & catalogo["activo"], "repo"].unique())
en_curso = [r for repo in repos_gh for r in runs_recientes(repo) if r["estado"] in ("queued", "in_progress")]
kpi_row([
    ("Ejecuciones 24 h", f"{len(ult24)}", NARANJA, "scripts individuales"),
    ("Fallidas 24 h", f"{int((~ult24['exito']).sum()) if len(ult24) else 0}", ROJO, "incluye timeouts"),
    ("En curso ahora", f"{len(en_curso)}", AZUL, "GitHub Actions"),
    ("Automatizaciones activas", f"{int(catalogo['activo'].sum())}", GRIS, f"de {len(catalogo)} en catálogo"),
])


# ------------------------------------------------------------------ En curso / mis solicitudes
@st.fragment(run_every=20)
def seguimiento():
    sol = st.session_state.get("ops_solicitudes", [])
    if sol:
        runs_recientes.clear()  # estado fresco de GitHub para las solicitudes de esta sesión
    curso =[r for repo in repos_gh for r in runs_recientes(repo) if r["estado"] in ("queued", "in_progress")]
    if not sol and not curso:
        return
    with st.container(border=True):
        st.markdown("**Seguimiento en vivo** · se actualiza cada 20 s")
        # Ejecuciones de n8n ya asignadas a un clic, para no asignar la misma a dos clics.
        ocupados = {s["ejecucion_id"] for s in sol if s.get("ejecucion_id")}
        for s in reversed(sol[-8:]):
            if s["plataforma"] == "github":
                run =buscar_run(s["repo"], s["request_id"])
                if run is None:
                    estado, url = "En cola (GitHub aún no la registra)", ""
                elif run["estado"] != "completed":
                    estado, url = "⟳ Ejecutando", run["url"]
                else:
                    estado = "✔ Exitosa" if run["conclusion"] == "success" else f"✖ {run['conclusion']}"
                    url = run["url"]
            else:
                if s.get("final"):  # ya terminó: no se vuelve a consultar n8n
                    info = s["resultado_n8n"]
                else:
                    info = estado_solicitud(s, ocupados - {s.get("ejecucion_id", "")})
                    if info["ejecucion_id"]:
                        s["ejecucion_id"] = info["ejecucion_id"]
                        ocupados.add(info["ejecucion_id"])
                    if info["final"]:
                        s["final"], s["resultado_n8n"] = True, info
                        st.toast(f"{s['nombre']}: {'terminó bien' if info['exito'] else 'falló'}",
                                 icon="✅" if info["exito"] else "❌")
                estado, url = info["texto"], info["url"]
            enlace = f" · [ver en n8n]({url})" if url and s.get("plataforma") == "n8n" else (
                f" · [ver ejecución]({url})" if url else "")
            st.markdown(f"- **{s['nombre']}** · {s['hora']} · {estado}{enlace}")
            if s.get("plataforma") == "n8n":
                if info.get("avance") is not None:
                    st.progress(info["avance"])
                if info.get("error"):
                    st.error(info["error"], icon="✖")
        otros = [r for r in curso if not any(s["request_id"] in r["titulo"] for s in sol)]
        for r in otros:
            st.markdown(f"- {r['repo']} · {r['titulo']} · ⟳ {r['estado']} · [ver]({r['url']})")


seguimiento()


def _ultima(item: pd.Series) -> tuple[str, str]:
    """Estado y texto de la última ejecución registrada."""
    script = str(item["script"])
    if script.startswith("lote:"):
        info = ultimo_lote(log, script.split(":", 1)[1]) if len(log) else None
        if not info:
            return "SIN DATOS", "Sin ejecuciones registradas"
        est = "EXITOSO" if info["fallidos"] == 0 else "FALLIDO"
        dur = (info["fin"] - info["inicio"]).total_seconds() / 60
        return est, (f"{info['inicio']:%d-%b %H:%M} · {info['scripts']} scripts · "
                     f"{info['fallidos']} fallidos · {dur:.0f} min")
    sub = log[log["automatizacion_id"].eq(item["automatizacion_id"])] if len(log) else log
    if sub.empty:
        return "SIN DATOS", "Sin ejecuciones registradas"
    u = sub.iloc[-1]
    return u["estado"], f"{u['fecha_inicio']:%d-%b %H:%M} · {u['duracion_seg']:.0f} s · {u['origen_grupo']}"


def tarjeta(item: pd.Series) -> None:
    estado, detalle = _ultima(item)
    with st.container(border=True):
        c1, c2 = st.columns([4, 1.3], vertical_alignment="center")
        with c1:
            plataforma = "n8n" if item["plataforma"] == "n8n" else "GitHub"
            extra = " · 🔒 sensible" if item["sensible"] else ""
            st.markdown(f"**{item['nombre']}**  \n"
                        f"<span style='color:#9A9A9A;font-size:0.8rem'>{plataforma} · "
                        f"{item['frecuencia']}{extra}</span>", unsafe_allow_html=True)
            st.markdown(badge(f"{ICONO_ESTADO.get(estado, '')} {estado}", COLOR_ESTADO.get(estado, GRIS))
                        + f"<span style='color:#AAAAAA;font-size:0.78rem;margin-left:8px'>{detalle}</span>",
                        unsafe_allow_html=True)
            if item.get("descripcion"):
                st.caption(item["descripcion"])
        with c2:
            # oct-2026: el botón vive en utils/ops_ui.py (lo comparte el Manual de automatizaciones)
            boton_ejecutar(item.to_dict(), usuario, admin)


# ------------------------------------------------------------------ Tarjetas por proyecto
activos = catalogo[catalogo["activo"]]
busqueda = st.text_input("Buscar automatización", placeholder="ej. JAE, satisfacción, lote…",
                         label_visibility="collapsed")
if busqueda:
    patron = busqueda.strip().lower()
    activos = activos[activos.apply(lambda r: patron in f"{r['nombre']} {r['script']} {r['proyecto']}".lower(), axis=1)]

proyectos = list(dict.fromkeys(activos["proyecto"]))
if not proyectos:
    st.info("No hay automatizaciones activas que coincidan.")
else:
    for pestaña, proyecto in zip(st.tabs(proyectos), proyectos):
        with pestaña:
            for _, item in activos[activos["proyecto"].eq(proyecto)].iterrows():
                tarjeta(item)

pendientes = catalogo[~catalogo["activo"]]
if len(pendientes):
    with st.expander(f"Pendientes de habilitar ({len(pendientes)})"):
        st.caption("Están en el catálogo pero sin botón: cada una explica qué falta. "
                   "Para activarla, corrige lo indicado y cambia 'activo' a SI en la hoja CATALOGO.")
        st.dataframe(pendientes[["nombre", "proyecto", "repo", "script", "descripcion"]],
                     hide_index=True, use_container_width=True)
