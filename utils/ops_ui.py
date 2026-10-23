"""
Botón "Ejecutar" compartido por el Panel de control y el Manual de automatizaciones.

Antes vivía dentro de pages/ops/1_Panel.py; se movió aquí (oct-2026) para que el
Manual dispare exactamente igual: misma regla de PIN para sensibles, mismo
registro en SOLICITUDES y mismo seguimiento en vivo del Panel
(st.session_state["ops_solicitudes"]).
"""
from __future__ import annotations

import time
from datetime import datetime

import streamlit as st

from utils.ops_auth import pin_valido
from utils.ops_data import TZ, registrar_solicitud
from utils.ops_dispatch import disparar_github, disparar_n8n, nuevo_request_id
from utils.ops_n8n import ultimo_id, ultimo_id_global


def disparar(item: dict, usuario: str) -> bool:
    rid = nuevo_request_id()
    base_id = base_global = None
    if item["plataforma"] == "n8n":
        base_id = ultimo_id(str(item.get("script", "")))  # para ubicar la ejecución de este clic
        base_global = ultimo_id_global()
        ok, msg = disparar_n8n(item, usuario, rid)
    else:
        ok, msg = disparar_github(item, usuario, rid)
    registrar_solicitud({
        "request_id": rid, "usuario": usuario, "automatizacion_id": item["automatizacion_id"],
        "nombre": item["nombre"], "plataforma": item["plataforma"],
        "resultado": "ENVIADA" if ok else "ERROR", "detalle": msg,
    })
    if ok:
        st.session_state.setdefault("ops_solicitudes", []).append({
            "request_id": rid, "nombre": item["nombre"], "repo": item["repo"],
            "plataforma": item["plataforma"], "hora": datetime.now(TZ).strftime("%H:%M"),
            # n8n: ID del flujo y hora del clic para ubicar su ejecución (utils/ops_n8n.py)
            "workflow_id": str(item.get("script", "")), "ts": time.time(), "base_id": base_id,
            "base_global": base_global, "timeout_min": item.get("timeout_min"),
        })
        st.toast(f"▶ {item['nombre']}: {msg}", icon="✅")
    else:
        st.toast(f"{item['nombre']}: {msg}", icon="⚠️")
    return ok


def boton_ejecutar(item: dict, usuario: str, admin: bool, prefijo: str = "") -> None:
    """Sensibles: PIN si no es admin, confirmación si es admin. Resto: botón directo."""
    clave = f"{prefijo}btn_{item['id']}"
    if item["sensible"] and not admin:
        with st.popover("▶ Ejecutar", use_container_width=True):
            st.caption("Automatización sensible: confirma con el PIN.")
            pin = st.text_input("PIN", type="password", key=f"{prefijo}pin_{item['id']}")
            if st.button("Confirmar ejecución", key=clave, type="primary"):
                if pin_valido(pin):
                    disparar(item, usuario)
                else:
                    st.error("PIN incorrecto")
    elif item["sensible"]:
        with st.popover("▶ Ejecutar", use_container_width=True):
            st.caption("Automatización sensible. ¿Confirmas?")
            if st.button("Sí, ejecutar", key=clave, type="primary"):
                disparar(item, usuario)
    elif st.button("▶ Ejecutar", key=clave, type="primary", use_container_width=True):
        disparar(item, usuario)
