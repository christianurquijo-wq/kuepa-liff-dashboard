"""
Query -- Ecolombia / Satisfacción (NPS).

Fuente: `Satisfaccion_ECOPLUS_2026` -- a diferencia de Overview/Académico
(que leen `Unificado_Satisfaccion`/`Unificado_Satisfaccion_APPEND`, vistas
que MEZCLAN 5 proyectos de Kuepa), esta tabla ya viene exclusiva de
Ecolombia 2.0 (814 filas totales, sin WHERE Proyecto=... necesario --
confirmado con scripts/inspect_schema.py: el conteo es idéntico al de
Unificado_Satisfaccion filtrada a Proyecto='Ecolombia 2.0').

Se traen pregunta_1..pregunta_17 (columnas crudas, sin nombre semántico)
en vez de las columnas ya agregadas Evaluacion_* de Unificado_Satisfaccion,
porque Christian compartió las fórmulas oficiales de agrupación de Looker
(ver utils/ecolombia_satisfaccion_metrics.py) y calcularlas directo sobre
las preguntas crudas es más auditable que confiar en el agregado de una
VIEW que además mezcla otros proyectos. pregunta_18 existe en el esquema
pero tiene CERO respuestas (0 de 814) -- no se trae.

`numero_de_documento_de_identidad` se trae porque la fórmula oficial de
NPS usa COUNT(numero_de_documento_de_identidad) como denominador (no
COUNT(pregunta_17)) -- ver docstring de nps_ecolombia().

`grupo` y `programa_que_cursas` se traen para las gráficas de desglose
que TODAVÍA no están confirmadas contra el pantallazo (ranking, barra por
Grupo, barra por Programa) -- ver nota de "pendientes" en
utils/ecolombia_satisfaccion_metrics.py y en la página.
"""

TABLA = "`sustained-edge-465417-m3.EFE_2026.Satisfaccion_ECOPLUS_2026`"

_PREGUNTAS = ", ".join(f"pregunta_{i}" for i in range(1, 18))

QUERY = f"""
SELECT
  modulo,
  grupo,
  programa_que_cursas,
  numero_de_documento_de_identidad,
  {_PREGUNTAS}
FROM {TABLA}
"""


def get_satisfaccion_query() -> str:
    return QUERY
