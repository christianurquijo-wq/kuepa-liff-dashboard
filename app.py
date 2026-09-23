"""
Punto de entrada del dashboard Kuepa en Streamlit.

Hasta LIFF Data, la navegación era automática: Streamlit descubre la
carpeta pages/ y lista cada archivo como una página suelta en la barra
lateral. Eso deja de servir en cuanto hay más de un proyecto -- todas las
páginas de todos los proyectos quedarían mezcladas, sin agrupar.

Desde aquí la navegación es EXPLÍCITA (st.navigation), agrupada por
proyecto: cada entrada del diccionario de abajo es el nombre de un
proyecto, y su lista de páginas aparece agrupada bajo ese nombre en la
barra lateral.

Dos cosas importantes de este cambio:
1. st.set_page_config() solo puede llamarse UNA VEZ por app, y tiene que
   ser aquí. Ningún archivo dentro de pages/ debe volver a llamarlo (por
   eso se quitó de pages/1_LIFF_Data.py) -- si dos archivos lo llaman,
   Streamlit lanza un error.
2. Como consecuencia de (1), el título de la pestaña del navegador ahora
   es fijo ("Kuepa Intelligence") para TODAS las páginas -- ya no cambia
   por página como antes (era "LIFF Data | Kuepa Intelligence", etc.).
   Es el tradeoff de agrupar la navegación así.

Para agregar un proyecto nuevo: crea su carpeta en pages/<proyecto>/,
agrega sus st.Page(...) aquí, y súmalos al diccionario de PROYECTOS.
"""
import streamlit as st

st.set_page_config(
    page_title="Kuepa Intelligence",
    page_icon="📊",
    layout="wide",
)

inicio = st.Page("pages/0_Inicio.py", title="Inicio", default=True)
liff_data = st.Page("pages/1_LIFF_Data.py", title="LIFF Data")
eco_overview = st.Page("pages/ecolombia/overview.py", title="Overview")
eco_academico = st.Page("pages/ecolombia/2_Academico.py", title="Académico")
eco_seleccion = st.Page("pages/ecolombia/3_Seleccion_Matricula.py", title="Selección y Matrícula")
eco_empleabilidad = st.Page("pages/ecolombia/4_Pool_Empleabilidad.py", title="Pool de Empleabilidad")
eco_satisfaccion = st.Page("pages/ecolombia/5_Satisfaccion.py", title="Satisfacción")
iq_overview = st.Page("pages/iq/1_Overview.py", title="Overview")
iq_historico = st.Page("pages/iq/2_Historico.py", title="Histórico")
iq_detalle = st.Page("pages/iq/3_Detalle_Consumo.py", title="Detalle de consumo")
iq_cobertura = st.Page("pages/iq/4_Cobertura.py", title="Cobertura")
iq_sheets = st.Page("pages/2_IQ.py", title="Usuarios y lecciones (Sheets)")

PROYECTOS = {
    "General": [inicio],
    "LIFF Data": [liff_data],
    "Ecolombia": [eco_overview, eco_academico, eco_seleccion, eco_empleabilidad, eco_satisfaccion],
    "IQ": [iq_overview, iq_historico, iq_detalle, iq_cobertura, iq_sheets],
}

pg = st.navigation(PROYECTOS)
pg.run()
