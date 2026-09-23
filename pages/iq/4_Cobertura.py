
import pandas as pd
import streamlit as st

from utils.iq_usage_hours import load_cobertura_huecos, load_cobertura_ventanas, usage_hours_actualizado_al
from utils.ui import badge, inject_css

inject_css()

st.markdown(badge("IQ · Cobertura y calidad de datos", "#29B6F6"), unsafe_allow_html=True)
st.title("Cobertura y calidad de datos")
st.caption(f"Datos de uso al {usage_hours_actualizado_al()} (fuente: `active_usage_hours`, BigQuery).")

huecos = load_cobertura_huecos()
ventanas = load_cobertura_ventanas()

st.markdown("### Huecos confirmados de exportación")
if huecos.empty:
    st.success("No hay huecos confirmados registrados.")
else:
    for _, h in huecos.iterrows():
        st.warning(
            f"**{h['desde']} → {h['hasta']}** ({h['dias']} días) -- {h['alcance']}. "
            "Ningún archivo exportado cubre este rango; los totales de Overview/Histórico "
            "para estos meses están por debajo de la actividad real."
        )
    st.caption(
        "Ambos huecos aparecieron pese a que la exportación se reportó como \"completa\" -- "
        "se detectaron cruzando el rango de fechas real (`created_at` mínimo/máximo) de cada "
        "archivo entregado, no confiando en el nombre del archivo ni en lo reportado de palabra."
    )

st.markdown("### Ventanas de cobertura por período")
st.dataframe(ventanas, hide_index=True, width="stretch")

st.markdown("### Otros hallazgos de calidad de datos")
st.markdown(
    """
- **148 filas duplicadas exactas** (mismo `_id`) se descartaron antes de agregar -- las 74
  duplicaciones detectadas pertenecen a un solo usuario en 2024; no afectan los totales de
  forma material, pero se documentan porque un `_id` duplicado no debería existir en la fuente.
- **`regional_name` NO es la provincia oficial de RD, es la Regional Educativa del MINERD**
  (~18 sedes, nombradas por su ciudad cabecera) -- se descubrió al construir el mapa: la primera
  versión usaba coordenadas de las 32 provincias oficiales y casi ningún valor calzaba (ej. la
  data trae "SAN FRANCISCO DE MACORIS", la provincia oficial de esa zona se llama "Duarte"). Se
  corrigió con un archivo de coordenadas nuevo (`data/iq/regiones_educativas_coords.csv`) armado
  a partir de los valores reales, no de la lista oficial de provincias.
- **Nombres sin normalizar en el origen**: la misma Regional aparece escrita de varias formas
  (con/sin tilde, con/sin cero a la izquierda en el código, y un typo "BAORUCO"/"BAHORUCO"). Se
  normalizó a mayúsculas sin tilde antes de agregar -- si en el futuro aparece una Regional nueva
  con otra grafía, el mapa de la página *Detalle de consumo* no la va a poder ubicar hasta que se
  agregue esa variante a la normalización.
- **Sin plataforma móvil antes de junio de 2023** ni en 2021-2022: coincide con una fecha de
  lanzamiento de producto, no se trata como hueco de exportación -- pero no está confirmado por
  Christian, solo inferido de los datos.
- **"Sin ubicación"**: usuarios sin centro educativo asignado (`regional_name` vacío o literal
  "USUARIO SIN CENTRO") se agrupan en su propio segmento, nunca se excluyen ni se intenta
  adivinar su provincia.
    """
)

st.markdown("### Usuarios y lecciones (hojas de Google Sheets)")
st.caption(
    "La calidad de datos de las hojas IQ_usuarios / IQ_lecciones (ID_SIS compartidos, "
    "autoverificación contra valores de referencia, carga masiva de IQ512) vive en la página "
    "**IQ (Sheets)** existente, sección \"Usuarios y calidad de datos\" -- no se duplica acá."
)
