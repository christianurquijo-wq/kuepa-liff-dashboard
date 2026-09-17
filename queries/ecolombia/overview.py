"""
Query -- Ecolombia / Overview.

A diferencia de LIFF Data, Ecolombia NO pasa por el bridge de n8n/Sheets:
el Service Account sí tiene acceso de lectura al proyecto de GCP
`sustained-edge-465417-m3` (confirmado), así que esta página consulta
BigQuery directo con utils/bigquery.run_query().

Selecciona SOLO las columnas que usa utils/ecolombia_metrics.py -- la tabla
real tiene 117 columnas (ver scripts/inspect_schema.py); no tiene sentido
traer todo para una página que hoy solo necesita 11.

`novedad_desercion` se quitó a propósito: es la misma columna duplicada
que `novedad` (siempre viene llena), y usarla como bandera de deserción
causó un bug real (100% de deserción reportado). Toda la lógica de estado
vive en `novedad` -- ver utils/ecolombia_metrics.py para el detalle
confirmado contra el pantallazo.

Pendiente: "Seleccionados" y "Pendientes por ingresar" (tarjetas del
pantallazo de Looker) no se pueden derivar de esta tabla -- necesitan la
tabla CONVOCATORIA, todavía sin explorar. Cuando se explore, esta función
probablemente se divida en dos (overview + convocatoria) o se le agregue
un JOIN.
"""

TABLA = "`sustained-edge-465417-m3.EFE_2026.ECOPLUS_V2_2026`"

QUERY = f"""
SELECT
  mes,
  cohorte,
  grupo,
  programa,
  ciudad,
  sexo,
  novedad,
  fecha_inicio_group_id,
  fecha_fin_group_id,
  cantidad_de_modulos_aprobados,
  fecha_de_finalizacionproductiva
FROM {TABLA}
"""


def get_overview_query() -> str:
    return QUERY
