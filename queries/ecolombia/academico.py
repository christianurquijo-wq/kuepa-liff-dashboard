"""
Query -- Ecolombia / Académico.

Misma tabla que Overview (`ECOPLUS_V2_2026`) -- la población base
(Activos/Deserciones/Retención) es idéntica, así que esta página reutiliza
utils.ecolombia_metrics.enrich() y kpis_overview() en vez de duplicar esa
lógica. Ver utils/ecolombia_academico_metrics.py para lo que sí es propio
de esta página (estado académico, Sankey, tabla de módulos).

cantidad_de_modulos_cursados y nota_modulo_0..7 se agregaron el
2026-09-17 al confirmar el esquema completo -- resolvieron los 3
pendientes de la primera versión (estado académico, Sankey, tabla por
módulo). modulo_que_cursa se trae para el filtro del mismo nombre del
pantallazo de Looker.
"""

TABLA = "`sustained-edge-465417-m3.EFE_2026.ECOPLUS_V2_2026`"

_NOTAS_MODULO = ", ".join(f"nota_modulo_{i}" for i in range(8))

QUERY = f"""
SELECT
  cohorte,
  grupo,
  programa,
  ciudad,
  sexo,
  novedad,
  modulo_que_cursa,
  cantidad_de_modulos_cursados,
  cantidad_de_modulos_aprobados,
  {_NOTAS_MODULO},
  fecha_de_finalizacionproductiva
FROM {TABLA}
"""


def get_academico_query() -> str:
    return QUERY
