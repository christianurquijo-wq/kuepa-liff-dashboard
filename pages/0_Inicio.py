"""
Página de inicio / portada del dashboard Kuepa.

Antes este contenido vivía en app.py. Se movió aquí porque app.py ahora
es solo el router (st.navigation) -- ver la nota en app.py sobre por qué.

oct-2026: se reemplazó el checklist de "Estado de la migración" (lenguaje
interno de desarrollo, sin valor para quien solo usa el dashboard) por un
menú de tarjetas -- una por proyecto, con una descripción corta y un botón
que lleva directo a la primera página de ese proyecto. Para agregar un
proyecto nuevo acá, sumá su tarjeta siguiendo el mismo patrón y actualizá
la ruta del st.page_link con la primera página que registraste en app.py.
"""
import streamlit as st

st.title("Kuepa Intelligence")
st.caption("Panel de indicadores académicos y de uso de Kuepa")

st.write("")
st.markdown("Elige un proyecto para comenzar:")
st.write("")

col1, col2, col3 = st.columns(3)

with col1, st.container(border=True):
    st.markdown("### 🎓 LIFF Data")
    st.caption(
        "Matrícula, avance académico y comparativo entre estudiantes "
        "extranjeros y nacionales."
    )
    st.page_link(
        "pages/1_LIFF_Data.py",
        label="Ir a LIFF Data",
        icon="➡️",
        use_container_width=True,
    )

with col2, st.container(border=True):
    st.markdown("### 🌎 Ecolombia")
    st.caption(
        "Selección, matrícula, avance académico, empleabilidad y "
        "satisfacción de los estudiantes."
    )
    st.page_link(
        "pages/ecolombia/1_Overview.py",
        label="Ir a Ecolombia",
        icon="➡️",
        use_container_width=True,
    )

with col3, st.container(border=True):
    st.markdown("### 📶 IQ")
    st.caption(
        "Uso de la plataforma, actividad de los usuarios y cobertura de datos."
    )
    st.page_link(
        "pages/iq/1_Analisis_Dinamico.py",
        label="Ir a IQ",
        icon="➡️",
        use_container_width=True,
    )
