"""
Página de inicio / portada del dashboard Kuepa.

oct-2026 (2): portada rediseñada -- una tarjeta por proyecto con color propio, descripción y
botón directo a su primera página, más el acceso al tablero de Socios Talento Capital 3.0 (que
vive en otra app de Streamlit, por eso abre en una pestaña nueva). Los otros tableros externos se
definen en utils/menu.py (OTROS_TABLEROS) y aparecen aquí y al final del menú lateral.

Para agregar un proyecto: suma un dict a TARJETAS con la ruta de la primera página que registraste
en app.py.
"""
import streamlit as st

from utils.menu import OTROS_TABLEROS

st.markdown(
    """
<style>
.inicio-hero {
  padding: 1.6rem 1.8rem; border-radius: 16px; margin-bottom: 1.4rem;
  background: radial-gradient(circle at 85% 0%, rgba(253,83,30,0.35) 0%, rgba(253,83,30,0.0) 55%),
              linear-gradient(135deg, #1E1E1E 0%, #171717 100%);
  border: 1px solid rgba(253,83,30,0.25);
}
.inicio-hero h1 { margin: 0; font-size: 2.1rem; }
.inicio-hero p { margin: 0.35rem 0 0 0; color: #BDBDBD; font-size: 1rem; }
.tarjeta-cab { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.2rem; }
.tarjeta-icono {
  width: 2.4rem; height: 2.4rem; border-radius: 10px; display: flex; align-items: center;
  justify-content: center; font-size: 1.3rem;
}
.tarjeta-titulo { font-size: 1.15rem; font-weight: 700; color: #FAFAFA; }
.tarjeta-etiqueta {
  font-size: 0.68rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
  padding: 2px 8px; border-radius: 10px; margin-left: auto;
}
.tarjeta-desc { color: #A8A8A8; font-size: 0.86rem; min-height: 3.6em; margin: 0.4rem 0 0.6rem 0; }
</style>
<div class="inicio-hero">
  <h1>Kuepa Intelligence</h1>
  <p>Indicadores académicos, de empleabilidad y de uso de la plataforma, y el control de las automatizaciones.
     Elige un proyecto para comenzar.</p>
</div>
""",
    unsafe_allow_html=True,
)

TARJETAS = [
    {"titulo": "EFE General", "icono": "📈", "color": "#FD531E", "etiqueta": "Requiere sesión",
     "desc": "Colsubsidio, Suba, Ecolombia y Jóvenes a la E: estado académico, tendencias, satisfacción, "
             "caracterización y empleabilidad.",
     "pagina": "pages/efe/1_Overview.py", "boton": "Ir a EFE General"},
    {"titulo": "LIFF Data", "icono": "🎓", "color": "#29B6F6", "etiqueta": "",
     "desc": "Matrícula, avance académico y comparativo entre estudiantes extranjeros y nacionales.",
     "pagina": "pages/1_LIFF_Data.py", "boton": "Ir a LIFF Data"},
    {"titulo": "Ecolombia", "icono": "🌎", "color": "#2ECC71", "etiqueta": "",
     "desc": "Selección, matrícula, avance académico, empleabilidad y satisfacción de los estudiantes.",
     "pagina": "pages/ecolombia/1_Overview.py", "boton": "Ir a Ecolombia"},
    {"titulo": "IQ", "icono": "📶", "color": "#F5B942", "etiqueta": "",
     "desc": "Uso de la plataforma, actividad de los usuarios y tipos de recurso consumidos.",
     "pagina": "pages/iq/1_Analisis_Dinamico.py", "boton": "Ir a IQ"},
    {"titulo": "Operaciones", "icono": "⚙️", "color": "#A569BD", "etiqueta": "Panel con sesión",
     "desc": "Ejecuta automatizaciones, revisa su historial y mira cuántas horas de trabajo manual ahorran.",
     "pagina": "pages/ops/1_Panel.py", "boton": "Ir al Panel de control"},
]


def cabecera(icono: str, titulo: str, color: str, etiqueta: str = "") -> None:
    chip = (f"<span class='tarjeta-etiqueta' style='background:{color}22;color:{color}'>{etiqueta}</span>"
            if etiqueta else "")
    st.markdown(
        f"<div class='tarjeta-cab'><div class='tarjeta-icono' style='background:{color}26'>{icono}</div>"
        f"<div class='tarjeta-titulo'>{titulo}</div>{chip}</div>"
        f"<div style='height:3px;border-radius:2px;background:linear-gradient(90deg,{color},transparent)'></div>",
        unsafe_allow_html=True)


# Tarjetas internas + tableros externos, en filas de 3
items = [("interna", t) for t in TARJETAS] + [("externa", t) for t in OTROS_TABLEROS]
for i in range(0, len(items), 3):
    cols = st.columns(3)
    for col, (tipo, t) in zip(cols, items[i:i + 3]):
        with col, st.container(border=True):
            if tipo == "interna":
                cabecera(t["icono"], t["titulo"], t["color"], t["etiqueta"])
                st.markdown(f"<div class='tarjeta-desc'>{t['desc']}</div>", unsafe_allow_html=True)
                st.page_link(t["pagina"], label=t["boton"], icon=":material/arrow_forward:",
                             use_container_width=True)
            else:
                cabecera(t["icono"], t["nombre"], "#FD531E", "Externo ↗")
                st.markdown(f"<div class='tarjeta-desc'>{t['descripcion']}</div>", unsafe_allow_html=True)
                st.link_button(f"Abrir {t['nombre']} ↗", t["url"], type="primary", use_container_width=True)

# Ayuda
st.write("")
with st.container(border=True):
    c1, c2, c3 = st.columns([3, 1.3, 1.3], vertical_alignment="center")
    with c1:
        cabecera("📘", "¿Necesitas ayuda?", "#8C8C8C")
        st.caption("Qué hace cada automatización y qué significa cada mensaje de error, en lenguaje práctico.")
    with c2:
        st.page_link("pages/ops/0_Manual.py", label="Manual", icon=":material/menu_book:", use_container_width=True)
    with c3:
        st.page_link("pages/ops/4_Errores.py", label="Errores frecuentes", icon=":material/help:",
                     use_container_width=True)
