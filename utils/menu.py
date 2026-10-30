"""
Menú lateral con identidad Kuepa (oct-2026).

Lo llama app.py en cada carga, antes de st.navigation, así aplica a TODAS las páginas:
  - logo de Kuepa arriba del menú (assets/logo-Kuepa.png),
  - secciones con color y separación, ítems con ícono, hover y la página activa resaltada,
  - accesos a otros tableros al final del menú (p. ej. Socios Talento Capital 3.0).

Los selectores (data-testid) son los del menú de st.navigation en Streamlit 1.4x–1.6x. Si una
versión futura los cambia, el menú sigue funcionando: solo pierde el estilo.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

LOGO = Path(__file__).resolve().parent.parent / "assets" / "logo-Kuepa.png"

# Otros tableros (fuera de esta app). Se muestran al final del menú y en el Inicio.
OTROS_TABLEROS = [
    {"nombre": "Socios Talento Capital 3.0", "url": "https://dash-general-stc.streamlit.app/",
     "descripcion": "Seguimiento general, formación, certificados y empleabilidad de STC 3.0.", "icono": "🤝"},
]

_CSS = """
<style>
/* ---------- fondo del menú ---------- */
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #1F1410 0%, #161616 22%, #141414 100%);
  border-right: 1px solid rgba(253, 83, 30, 0.18);
}
/* ---------- encabezado de cada sección ---------- */
[data-testid="stNavSectionHeader"] {
  margin-top: 0.9rem;
  padding: 0.35rem 0.6rem 0.35rem 0.55rem;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.035);
  border-left: 3px solid rgba(253, 83, 30, 0.55);
}
[data-testid="stNavSectionHeader"] p {
  font-size: 0.74rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #F2F2F2 !important;
}
/* ---------- ítems ---------- */
[data-testid="stSidebarNavLink"] {
  border-radius: 8px;
  margin: 1px 0 1px 0.35rem;
  padding-left: 0.6rem;
  border-left: 3px solid transparent;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
}
[data-testid="stSidebarNavLink"] p { font-size: 0.9rem; color: #CFCFCF; }
[data-testid="stSidebarNavLink"] [data-testid="stIconMaterial"] { color: #8C8C8C !important; }
[data-testid="stSidebarNavLink"]:hover {
  background: rgba(253, 83, 30, 0.10);
  transform: translateX(2px);
}
[data-testid="stSidebarNavLink"]:hover p { color: #FFFFFF; }
[data-testid="stSidebarNavLink"]:hover [data-testid="stIconMaterial"] { color: #FD8A5E !important; }
/* ---------- página activa ---------- */
[data-testid="stSidebarNavLink"][aria-current="page"] {
  background: linear-gradient(90deg, rgba(253, 83, 30, 0.28) 0%, rgba(253, 83, 30, 0.08) 100%);
  border-left: 3px solid #FD531E;
}
[data-testid="stSidebarNavLink"][aria-current="page"] p { color: #FFFFFF; font-weight: 700; }
[data-testid="stSidebarNavLink"][aria-current="page"] [data-testid="stIconMaterial"] { color: #FD531E !important; }
/* ---------- logo ---------- */
[data-testid="stSidebarHeader"] img, [data-testid="stLogo"] { height: 2.6rem !important; max-width: 11rem; }
/* ---------- bloque "Otros tableros" ---------- */
.menu-otros-titulo {
  font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
  color: #9A9A9A; margin: 0.4rem 0 0.3rem 0.2rem;
}
</style>
"""


def decorar_menu() -> None:
    if LOGO.exists():
        st.logo(str(LOGO), size="large")
    st.markdown(_CSS, unsafe_allow_html=True)
    with st.sidebar:
        st.divider()
        st.markdown('<div class="menu-otros-titulo">↗ Otros tableros</div>', unsafe_allow_html=True)
        for t in OTROS_TABLEROS:
            st.link_button(f"{t['icono']} {t['nombre']}", t["url"], use_container_width=True, help=t["descripcion"])
