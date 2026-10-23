"""
Seguimiento en vivo de flujos de n8n vía su API pública (oct-2026).

El panel dispara el webhook y luego consulta aquí las ejecuciones del flujo para
mostrar: en curso / exitoso / falló, duración, avance por nodos, nodo y mensaje
de error, y el enlace a la ejecución.

Secrets de Streamlit (sección [ops]):
    n8n_api_url = "https://n8n.kuepa.com/api/v1"
    n8n_api_key = "..."   # n8n → Settings → n8n API → Create an API key

Notas:
- El CATALOGO debe tener el ID del flujo en la columna `script` (filas n8n).
- El avance por nodos MIENTRAS corre solo existe si el flujo tiene activado
  "Save execution progress" (Workflow settings). Sin eso, n8n solo guarda los
  nodos al terminar: el panel muestra "Ejecutando" sin el conteo.
- La lógica pura (sin Streamlit ni red) está en las funciones `_…` para probarla.
"""
from __future__ import annotations

from datetime import datetime, timezone

import requests
import streamlit as st

FINALES = {"success", "error", "crashed", "canceled"}
ETIQUETA = {
    "new": "⟳ En cola en n8n",
    "running": "⟳ Ejecutando",
    "waiting": "⏸ En espera (nodo Wait)",
    "success": "✔ Exitosa",
    "error": "✖ Falló",
    "crashed": "✖ Se cayó (crashed)",
    "canceled": "■ Cancelada",
}


def configurado() -> bool:
    ops = st.secrets.get("ops", {})
    return bool(ops.get("n8n_api_url") and ops.get("n8n_api_key"))


def _base() -> str:
    return str(st.secrets["ops"]["n8n_api_url"]).rstrip("/")


def _get(ruta: str, **params) -> dict:
    r = requests.get(f"{_base()}{ruta}", params=params, timeout=15,
                     headers={"X-N8N-API-KEY": st.secrets["ops"]["n8n_api_key"], "Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def url_ejecucion(workflow_id: str, ejecucion_id: str) -> str:
    raiz = _base().split("/api/")[0]
    return f"{raiz}/workflow/{workflow_id}/executions/{ejecucion_id}"


@st.cache_data(ttl=8, show_spinner=False)
def ejecuciones(workflow_id: str) -> list[dict]:
    """Últimas ejecuciones del flujo (incluye las que siguen corriendo, si la versión de n8n las lista)."""
    return _get("/executions", workflowId=workflow_id, limit=10).get("data", [])


@st.cache_data(ttl=600, show_spinner=False)
def total_nodos(workflow_id: str) -> int:
    """Nodos ejecutables del flujo (sin notas adhesivas)."""
    nodos = _get(f"/workflows/{workflow_id}").get("nodes", [])
    return sum(1 for n in nodos if "stickyNote" not in str(n.get("type", "")))


@st.cache_data(ttl=8, show_spinner=False)
def detalle(ejecucion_id: str) -> dict:
    return _get(f"/executions/{ejecucion_id}", includeData="true")


# ------------------------------------------------------------------ lógica pura
def _ts(valor) -> float | None:
    if not valor:
        return None
    return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).timestamp()


def _elegir(lista: list[dict], desde_ts: float, ocupados: set[str]) -> dict | None:
    """La primera ejecución por webhook que arrancó después del clic (margen 20 s por reloj)
    y que no se haya asignado ya a otro clic de la misma sesión."""
    candidatas = [e for e in lista
                  if str(e.get("mode")) == "webhook"
                  and (_ts(e.get("startedAt")) or 0) >= desde_ts - 20
                  and str(e.get("id")) not in ocupados]
    return min(candidatas, key=lambda e: _ts(e.get("startedAt")) or 0) if candidatas else None


def _resumen_detalle(det: dict) -> dict:
    """Extrae nodos ejecutados, último nodo y error de GET /executions/{id}?includeData=true."""
    res = ((det.get("data") or {}).get("resultData") or {})
    error = res.get("error") or {}
    nodo_error = (error.get("node") or {}).get("name") if isinstance(error.get("node"), dict) else error.get("node")
    mensaje = error.get("message") or error.get("description") or ""
    return {
        "nodos": len(res.get("runData") or {}),
        "ultimo_nodo": res.get("lastNodeExecuted") or "",
        "nodo_error": nodo_error or (res.get("lastNodeExecuted") if mensaje else ""),
        "mensaje": str(mensaje)[:400],
    }


def _duracion(inicio, fin, ahora_ts: float) -> float | None:
    a = _ts(inicio)
    if a is None:
        return None
    return (_ts(fin) or ahora_ts) - a


def _fmt_dur(seg: float | None) -> str:
    if seg is None:
        return ""
    seg = max(0, int(seg))
    return f"{seg // 60} min {seg % 60:02d} s" if seg >= 60 else f"{seg} s"


# ------------------------------------------------------------------ para el panel
def estado_solicitud(sol: dict, ocupados: set[str]) -> dict:
    """Estado legible de un clic a un flujo de n8n. Nunca lanza excepción.

    Devuelve: texto, final (bool), exito (bool|None), url, ejecucion_id, error, avance."""
    wf = str(sol.get("workflow_id") or "")
    base = {"final": False, "exito": None, "url": "", "ejecucion_id": "", "error": "", "avance": None}
    if not configurado():
        return {**base, "texto": "Enviada a n8n · falta n8n_api_key en Secrets para seguirla en vivo"}
    if not wf or wf.startswith("ID_"):
        return {**base, "texto": "Enviada a n8n · el CATALOGO no tiene el ID del flujo (columna script)"}
    ahora = datetime.now(timezone.utc).timestamp()
    try:
        if sol.get("ejecucion_id"):  # ya ubicada en una vuelta anterior: se consulta directo
            ej = detalle(str(sol["ejecucion_id"]))
        else:
            ej = _elegir(ejecuciones(wf), float(sol.get("ts") or 0), ocupados)
    except requests.RequestException as exc:
        return {**base, "texto": f"Enviada a n8n · no se pudo consultar su API ({type(exc).__name__})"}
    if ej is None:
        espera = ahora - float(sol.get("ts") or ahora)
        texto = ("⟳ Iniciando en n8n…" if espera < 90 else
                 "Enviada a n8n · aún no aparece la ejecución (¿el flujo no guarda ejecuciones por webhook?)")
        return {**base, "texto": texto}

    eid, estado = str(ej.get("id")), str(ej.get("status") or ("success" if ej.get("finished") else "running"))
    out = {**base, "ejecucion_id": eid, "url": url_ejecucion(wf, eid), "final": estado in FINALES,
           "exito": (estado == "success") if estado in FINALES else None}
    dur = _fmt_dur(_duracion(ej.get("startedAt"), ej.get("stoppedAt"), ahora))
    partes = [ETIQUETA.get(estado, estado), dur]
    try:
        info = _resumen_detalle(detalle(eid))
        total = total_nodos(wf)
        if info["nodos"] and not out["final"]:
            out["avance"] = min(info["nodos"] / total, 0.99) if total else None
            partes.append(f"{info['nodos']} de {total} nodos · en «{info['ultimo_nodo']}»")
        if estado in FINALES and estado != "success":
            out["error"] = (f"Nodo «{info['nodo_error']}»: " if info["nodo_error"] else "") + (info["mensaje"] or estado)
    except requests.RequestException:
        pass  # sin detalle: se muestra solo estado y duración
    out["texto"] = " · ".join(p for p in partes if p)
    return out
