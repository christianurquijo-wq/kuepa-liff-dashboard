"""
Operaciones -- Errores frecuentes (oct-2026).

Catálogo en lenguaje práctico de los mensajes de error del Panel de control, de las
automatizaciones y de las páginas de EFE: qué pasó, qué puede hacer la persona y cuándo reportarlo.
PÚBLICA (no tiene datos). El contenido vive en utils/ops_errores.py (el mismo que usan los avisos
explicados del Panel y la pestaña «Si algo falla» del Manual).
"""
import streamlit as st

from utils.ops_errores import render_catalogo
from utils.ui import inject_css

inject_css()
st.title("🧭 Errores frecuentes")
st.caption("Si te apareció un mensaje de error (404, 403, 500…), aquí está qué significa y qué hacer. "
           "En el Panel, los errores ya aparecen explicados con un botón para reportarlos al equipo.")
render_catalogo("err")
