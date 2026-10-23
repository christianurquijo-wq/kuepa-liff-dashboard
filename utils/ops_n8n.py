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
    """Últimas 50 ejecuciones del flujo (50 para que un clic no quede tapado por las programadas) (incluye las que siguen corriendo, si la versión de n8n las lista)."""
    return _get("/executions", workflowId=workflow_id, limit=50).get("data", [])


@st.cache_data(ttl=600, show_spinner=False)
def total_nodos(workflow_id: str) -> int:
    """Nodos ejecutables del flujo (sin notas adhesivas)."""
    nodos = _get(f"/workflows/{workflow_id}").get("nodes", [])
    return sum(1 for n in nodos if "stickyNote" not in str(n.get("type", "")))


@st.cache_data(ttl=8, show_spinner=False)
def detalle(ejecucion_id: str) -> dict:
    return _get(f"/executions/{ejecucion_id}", includeData="true")


_PISTAS = {
    401: "401: la n8n_api_key no es válida o fue revocada",
    403: "403: la API pública de n8n está deshabilitada o la key no tiene permiso",
    404: "404: revisa n8n_api_url (debe terminar en /api/v1) o el ID del flujo en el CATALOGO",
}


def _explicar(exc: requests.RequestException) -> str:
    """Código HTTP y pista concreta, sin exponer la key."""
    resp = getattr(exc, "response", None)
    if resp is None:
        return f"sin conexión: {type(exc).__name__}"
    codigo = resp.status_code
    detalle = ""
    try:
        detalle = str(resp.json().get("message", ""))[:120]
    except ValueError:
        pass
    return _PISTAS.get(codigo, f"HTTP {codigo}") + (f" · {detalle}" if detalle else "")


# ------------------------------------------------------------------ lógica pura
def _ts(valor) -> float | None:
    if not valor:
        return None
    d = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    if d.tzinfo is None:  # n8n sin zona: se asume UTC (no la hora del servidor de Streamlit)
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def _num(ejecucion_id) -> int:
    try:
        return int(str(ejecucion_id))
    except ValueError:
        return -1


def ultimo_id(workflow_id: str) -> int | None:
    """ID de la ejecución más reciente del flujo justo ANTES de disparar. Los IDs de n8n son
    crecientes: la del clic será la primera mayor a este, sin depender de relojes ni zonas."""
    if not configurado() or not workflow_id or workflow_id.startswith("ID_"):
        return None
    try:
        datos = _get("/executions", workflowId=workflow_id, limit=1).get("data", [])
    except requests.RequestException:
        return None
    return _num(datos[0]["id"]) if datos else 0


def ultimo_id_global() -> int | None:
    """ID de la ejecución más reciente de TODO n8n antes del clic (los IDs son globales y crecientes)."""
    if not configurado():
        return None
    try:
        datos = _get("/executions", limit=1).get("data", [])
    except requests.RequestException:
        return None
    return _num(datos[0]["id"]) if datos else 0


@st.cache_data(ttl=8, show_spinner=False)
def _cabecera(ejecucion_id: int) -> dict | None:
    """Ejecución por ID (sin datos de nodos). None si aún no existe."""
    try:
        return _get(f"/executions/{ejecucion_id}")
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        raise


def _sondear(workflow_id: str, base_global: int, ocupados: set[str], max_ids: int = 12) -> dict | None:
    """El listado de la API pública de n8n NO incluye las ejecuciones que siguen corriendo.
    Como los IDs son consecutivos en todo n8n, se consultan uno a uno los posteriores al clic
    hasta dar con la de este flujo (para en el primer ID que aún no existe)."""
    for eid in range(base_global + 1, base_global + 1 + max_ids):
        cab = _cabecera(eid)
        if cab is None:
            return None
        if str(cab.get("workflowId")) == workflow_id and str(eid) not in ocupados:
            return cab
    return None


def _elegir(lista: list[dict], desde_ts: float, ocupados: set[str], base_id: int | None = None) -> dict | None:
    """La primera ejecución por webhook que arrancó después del clic (margen 20 s por reloj)
    y que no se haya asignado ya a otro clic de la misma sesión."""
    if base_id is not None:  # criterio principal: ID mayor al último antes del clic
        despues = [e for e in lista if _num(e.get("id")) > base_id and str(e.get("id")) not in ocupados]
    else:                    # respaldo: por hora de inicio
        despues = [e for e in lista
                   if (_ts(e.get("startedAt")) or 0) >= desde_ts - 20 and str(e.get("id")) not in ocupados]
    # Se prefieren las de modo webhook; si n8n las reporta con otro modo, se toma la primera igual.
    candidatas = [e for e in despues if str(e.get("mode")) == "webhook"] or despues
    return min(candidatas, key=lambda e: _num(e.get("id"))) if candidatas else None


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


def _estimado(espera: float, tipica: float | None) -> tuple[float | None, str]:
    """Opción A: avance estimado con la duración típica (mediana de las exitosas en el LOG)."""
    if not tipica or tipica <= 0:
        return None, ""
    if espera > tipica * 1.5:
        return 0.95, f"más de lo habitual (suele tardar {_fmt_dur(tipica)})"
    pct = min(espera / tipica, 0.95)
    return pct, f"≈ {pct * 100:.0f} % · suele tardar {_fmt_dur(tipica)}"


def aplicar_progreso(info: dict, prog: dict | None) -> dict:
    """Opción B: si el flujo reportó su paso en la hoja PROGRESO, reemplaza el estimado por el
    paso real ("Paso 3 de 9: CRM (Backup)") y la barra exacta. No toca los finales."""
    if not prog or info.get("final"):
        return info
    try:
        n, total = int(float(prog.get("paso_n") or 0)), int(float(prog.get("total_pasos") or 0))
    except (TypeError, ValueError):
        return info
    if not total:
        return info
    base = info["texto"].split(" · ")[0]
    if base.startswith("⟳ Iniciando"):
        base = "⟳ Ejecutando"
    return {**info, "avance": min(n / total, 0.99),
            "texto": f"{base} · Paso {n} de {total}: {prog.get('paso', '')}"
                     + (f" · {prog.get('actualizado')}" if prog.get("actualizado") else "")}


# ------------------------------------------------------------------ para el panel
def estado_solicitud(sol: dict, ocupados: set[str], tipica: float | None = None) -> dict:
    """Estado legible de un clic a un flujo de n8n. Nunca lanza excepción.

    Devuelve: texto, final (bool), exito (bool|None), url, ejecucion_id, error, avance."""
    wf = str(sol.get("workflow_id") or "")
    base = {"final": False, "exito": None, "url": "", "ejecucion_id": "", "error": "", "avance": None}
    if not configurado():
        return {**base, "texto": "Enviada a n8n · falta n8n_api_key en Secrets para seguirla en vivo"}
    if not wf or wf.startswith("ID_"):
        return {**base, "texto": "Enviada a n8n · el CATALOGO no tiene el ID del flujo (columna script)"}
    ahora = datetime.now(timezone.utc).timestamp()
    lista: list[dict] = []
    try:
        if sol.get("ejecucion_id"):  # ya ubicada en una vuelta anterior: se consulta directo
            ej = detalle(str(sol["ejecucion_id"]))
        else:
            lista = ejecuciones(wf)
            ej = _elegir(lista, float(sol.get("ts") or 0), ocupados, sol.get("base_id"))
            if ej is None and sol.get("base_global") is not None:  # aún corriendo: no sale en el listado
                ej = _sondear(wf, int(sol["base_global"]), ocupados)
    except requests.RequestException as exc:
        return {**base, "texto": f"Enviada a n8n · no se pudo consultar su API ({_explicar(exc)})"}
    if ej is None:
        espera = ahora - float(sol.get("ts") or ahora)
        limite = max(float(sol.get("timeout_min") or 30), 30) * 60
        avance, est = _estimado(espera, tipica)
        if espera < limite:  # lo normal: la API de n8n solo publica la ejecución al terminar
            texto = (f"⟳ {'Iniciando' if espera < 30 else 'En proceso'} en n8n · {_fmt_dur(espera)} desde el clic"
                     + (f" · {est}" if est else " (n8n la mostrará con su resultado al terminar)"))
            return {**base, "texto": texto, "avance": avance}
        else:  # pista para diagnosticar: qué flujo se consultó y qué tiene guardado
            ultima = max((str(e.get("startedAt", ""))[:16].replace("T", " ") for e in lista), default="ninguna")
            texto = (f"Enviada a n8n · no aparece su ejecución en el flujo {wf} "
                     f"({len(lista)} guardadas, última: {ultima} UTC). Revisa el ID en el CATALOGO "
                     "y que el flujo guarde ejecuciones")
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
        elif not out["final"]:
            out["avance"], est = _estimado(_duracion(ej.get("startedAt"), None, ahora) or 0, tipica)
            if est:
                partes.append(est)
        if estado in FINALES and estado != "success":
            out["error"] = (f"Nodo «{info['nodo_error']}»: " if info["nodo_error"] else "") + (info["mensaje"] or estado)
    except requests.RequestException:
        pass  # sin detalle: se muestra solo estado y duración
    out["texto"] = " · ".join(p for p in partes if p)
    return out
