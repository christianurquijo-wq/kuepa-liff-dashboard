"""
Control de acceso del Panel de Operaciones.

El dashboard es público, pero Operaciones dispara procesos reales, así que:
  1. Login con Google (st.login, OIDC) -> sabemos QUIÉN presionó cada botón.
  2. Lista de correos autorizados en st.secrets["ops"]["usuarios"]
     (o un dominio completo con st.secrets["ops"]["dominio"] = "kuepa.com").
  3. Botones marcados como sensibles en el CATALOGO piden además un PIN
     (st.secrets["ops"]["pin_sensible"]). Los admins no necesitan PIN.

Las páginas de LIFF / Ecolombia / IQ siguen públicas: nada de esto las toca.
"""
from __future__ import annotations

import hmac

import streamlit as st


def _ops() -> dict:
    return dict(st.secrets.get("ops", {}))


def _correo() -> str:
    return str(getattr(st.user, "email", "") or "").strip().lower()


def requiere_login(titulo: str = "Operaciones",
                   mensaje: str = "Esta sección dispara procesos reales. Inicia sesión con tu cuenta de Google de Kuepa.",
                   ) -> str:
    """Corta la página si no hay sesión autorizada. Devuelve el correo.
    oct-2026: titulo/mensaje opcionales para reutilizar el mismo login en EFE General
    (misma lista de usuarios del Panel de control)."""
    if "auth" not in st.secrets:
        st.error(
            "Falta configurar el login con Google ([auth] en los secrets de Streamlit). "
            "Ver GUIA_PANEL_OPERACIONES.md, paso 3."
        )
        st.stop()

    if not st.user.is_logged_in:
        st.title(titulo)
        st.info(mensaje)
        st.button("Iniciar sesión con Google", type="primary", on_click=st.login)
        st.stop()

    correo = _correo()
    cfg = _ops()
    usuarios = {u.strip().lower() for u in cfg.get("usuarios", [])}
    admins = {u.strip().lower() for u in cfg.get("admins", [])}
    dominio = str(cfg.get("dominio", "")).strip().lower()
    autorizado = correo in usuarios or correo in admins or (dominio and correo.endswith("@" + dominio))
    if not autorizado:
        st.error(f"La cuenta {correo} no está autorizada para {titulo}. Pide acceso a Christian.")
        st.button("Cerrar sesión", on_click=st.logout)
        st.stop()

    with st.sidebar:
        st.caption(f"Sesión: {correo}")
        st.button("Cerrar sesión", on_click=st.logout, key="ops_logout")
    return correo


def sesion_opcional() -> tuple[str | None, bool]:
    """Como requiere_login(), pero SIN cortar la página: para páginas de consulta
    (Manual) que cualquiera puede ver y que solo piden login para ejecutar.
    Devuelve (correo o None, autorizado)."""
    if "auth" not in st.secrets or not st.user.is_logged_in:
        return None, False
    correo = _correo()
    cfg = _ops()
    usuarios = {u.strip().lower() for u in cfg.get("usuarios", [])}
    admins = {u.strip().lower() for u in cfg.get("admins", [])}
    dominio = str(cfg.get("dominio", "")).strip().lower()
    autorizado = correo in usuarios or correo in admins or bool(dominio and correo.endswith("@" + dominio))
    return correo, autorizado


def es_admin(correo: str) -> bool:
    return correo.lower() in {u.strip().lower() for u in _ops().get("admins", [])}


def pin_valido(pin: str) -> bool:
    esperado = str(_ops().get("pin_sensible", ""))
    if not esperado:
        return False  # sin PIN configurado, los botones sensibles quedan bloqueados (salvo admins)
    return hmac.compare_digest(pin.strip().encode(), esperado.encode())
