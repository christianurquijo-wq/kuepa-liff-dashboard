"""
Página de inicio / portada del dashboard Kuepa.

Antes este contenido vivía en app.py. Se movió aquí porque app.py ahora
es solo el router (st.navigation) -- ver la nota en app.py sobre por qué.
"""
import streamlit as st

st.title("Kuepa Intelligence")
st.caption("Dashboard académico -- migración de n8n a Streamlit")

st.markdown(
    """
    Usa el menú de la izquierda para navegar entre proyectos y sus páginas.

    **Estado de la migración:**
    - ✅ LIFF Data -- completo (KPIs, filtros, comparativo extranjeros vs nacionales)
    - ✅ Ecolombia -- completo (Overview, Académico, Selección y Matrícula, Pool de Empleabilidad, Satisfacción)
    - ✅ IQ -- completo (Resumen y recencia, Uso y tiempo, Lecciones consumidas, Usuarios y calidad de datos)
    """
)
