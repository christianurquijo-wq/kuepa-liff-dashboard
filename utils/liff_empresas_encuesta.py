"""
Resultados de la encuesta a empresas -- "¿Está interesado en contratar
practicantes extranjeros?" (oct-2026). Se usa en pages/1_LIFF_Data.py,
pestaña "Caracterización y satisfacción", bloque final.

Datos HARDCODEADOS a propósito (decisión de Christian): es una encuesta
cerrada con resultados fijos, así que no se justifica una hoja de Sheets
ni un secret extra. Para actualizar cifras o empresas, basta con editar
este archivo y hacer push (el resto de la página se recalcula solo).

Reglas de consistencia (se validan al importar, para que un typo al editar
rompa con un mensaje claro en vez de mostrar números que no cuadran):
  - la suma de empresas por sector debe ser igual a EMPRESAS_ACEPTAN;
  - EMPRESAS_ACEPTAN <= EMPRESAS_RESPONDIERON <= EMPRESAS_ENCUESTADAS.
"""

EMPRESAS_ENCUESTADAS = 262   # empresas a las que se les envió la encuesta
EMPRESAS_RESPONDIERON = 18  # respondieron la pregunta de interés
EMPRESAS_ACEPTAN = 18        # respondieron que SÍ contratarían practicantes extranjeros

# sector -> empresas que aceptan. El orden del dict es el orden de
# presentación (de más a menos empresas; los de 1 empresa al final).
EMPRESAS_ACEPTAN_POR_SECTOR: dict[str, list[str]] = {
    "BPO y contact center": ["Abai", "Atento", "Emergia", "Megalínea", "Millenium", "Scotia GBS", "Synerjoy"],
    "Financiero y seguros": ["Santander", "Bold", "Sura"],
    "Energía y servicios públicos": ["Chilco", "Doña Juana"],
    "Comercio": ["OXXO"],
    "Hotelería": ["Dann Carlton"],
    "Tecnología": ["Cerca"],
    "Investigación de mercados": ["Dichter & Neira"],
    "Servicios empresariales": ["Iron Mountain"],
    "Laboratorios clínicos": ["Colcan"],
}

assert sum(len(v) for v in EMPRESAS_ACEPTAN_POR_SECTOR.values()) == EMPRESAS_ACEPTAN, (
    "utils/liff_empresas_encuesta.py: la suma de empresas por sector no coincide con EMPRESAS_ACEPTAN"
)
assert EMPRESAS_ACEPTAN <= EMPRESAS_RESPONDIERON <= EMPRESAS_ENCUESTADAS, (
    "utils/liff_empresas_encuesta.py: debe cumplirse aceptan <= respondieron <= encuestadas"
)
