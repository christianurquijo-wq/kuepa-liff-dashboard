"""
Consultas de la sección EFE General (migración de «Dash General EFE2» de n8n, oct-2026).

Fuente: sustained-edge-465417-m3.EFE_2026
  - Vistas Unificado_* (estado actual, una fila por persona x programa / encuesta).
  - Tablas *_APPEND (foto MENSUAL, Fecha_Append = 'AAAA-MM', hasta antes de la foto diaria).
  - Tablas *_DIARIO (foto DIARIA, la escribe EFE/Foto_diaria_EFE.py cada noche).

Por qué así y no como en n8n:
  - n8n hacía SELECT * en cada visita y armaba un HTML con TODAS las filas adentro. Aquí las
    vistas actuales son pequeñas (miles de filas) y se cachean 10 min (utils/bigquery.run_query).
  - Las series de tiempo (foto diaria/mensual) crecen todos los días, así que NUNCA se bajan
    fila por fila: se agregan en BigQuery (conteos por fecha x proyecto x programa).
  - Documento es INTEGER en Seguimiento/Empleabilidad y STRING en las otras: todo se lleva a
    texto para poder cruzar.
  - Las reglas de negocio (impactado, retenido, desertor) viven en UN solo lugar:
    utils/efe_metrics.py, y estas consultas las reciben de ahí.
"""
from __future__ import annotations

DATASET = "sustained-edge-465417-m3.EFE_2026"


def _t(tabla: str) -> str:
    return f"`{DATASET}.{tabla}`"


def _lista(valores) -> str:
    return ", ".join("'" + v.replace("'", "\\'") + "'" for v in sorted(valores))


# --------------------------------------------------------------------------- estado actual
def seguimiento(con_nombre: bool = False) -> str:
    nombre = "NULLIF(TRIM(Nombre), '') AS Nombre,\n      " if con_nombre else ""
    return f"""
    SELECT
      {nombre}CAST(Documento AS STRING) AS Documento,
      Proyecto, Programa, Estado_academico, Resultado_academico, Ciudad, Sexo,
      Fecha_ingreso_formacion, Fecha_fin_formacion
    FROM {_t('Unificado_Seguimiento')}
    WHERE Documento IS NOT NULL
    """


def satisfaccion() -> str:
    return f"""
    SELECT
      CAST(Documento AS STRING) AS Documento, Proyecto, Fecha,
      Evaluacion_docente, Evaluacion_recursos_contenido, Evaluacion_institucion,
      Evaluacion_plataforma, Evaluacion_empleabilidad, Evaluacion_psicosocial,
      Autoevaluacion, NPS, Promedio_Satisfaccion
    FROM {_t('Unificado_Satisfaccion')}
    """


def caracterizacion() -> str:
    return f"""
    SELECT
      CAST(Documento AS STRING) AS Documento, Proyecto, Fecha, Sexo, Edad, Estrato,
      Actividad_principal, Ingresos, Escolaridad, Numero_hijos_Personas_cargo, Ciudad_residencia
    FROM {_t('Unificado_Caracterizacion')}
    """


def empleabilidad() -> str:
    return f"""
    SELECT
      CAST(Documento AS STRING) AS Documento, Proyecto, Ciudad, Estado_contratacion,
      Estado_academico, Total_remisiones_postulaciones, Empresa
    FROM {_t('Unificado_Empleabilidad')}
    WHERE Documento IS NOT NULL
    """


# --------------------------------------------------------------------------- series de tiempo
def _serie_seguimiento(origen_sql: str, fecha_sql: str, etiqueta: str,
                       impactado: set, retenido: set, desercion: set) -> str:
    """KPIs académicos por fecha x proyecto x programa, más el total por proyecto
    (Programa = '(Todos)'). Personas = documentos distintos; las tasas se calculan sobre
    inscripciones (persona x programa) -- ver utils/efe_metrics.py."""
    est = "LOWER(TRIM(Estado_academico))"
    res = "LOWER(TRIM(Resultado_academico))"
    imp = f"{est} IN ({_lista({e.lower() for e in impactado})})"
    ret = f"{est} IN ({_lista({e.lower() for e in retenido})})"
    des = f"{est} IN ({_lista({e.lower() for e in desercion})})"
    return f"""
    WITH base AS (
      -- DISTINCT: en las APPEND el mismo mes puede quedar cargado más de una vez
      SELECT DISTINCT {fecha_sql} AS Fecha, CAST(Documento AS STRING) AS Documento,
             Proyecto, COALESCE(NULLIF(TRIM(Programa), ''), 'Sin programa') AS Prog,
             Estado_academico, Resultado_academico
      FROM {origen_sql}
      WHERE Documento IS NOT NULL
    )
    SELECT
      '{etiqueta}' AS Origen, Fecha, Proyecto,
      IF(GROUPING(Prog) = 1, '(Todos)', Prog) AS Programa,  -- alias distinto al de base: sin ambigüedad en GROUP BY
      COUNT(DISTINCT Documento) AS personas,
      COUNT(DISTINCT IF({imp}, Documento, NULL)) AS impactados,
      COUNT(DISTINCT IF({est} = 'activo', Documento, NULL)) AS activos,
      COUNT(DISTINCT IF({est} = 'finalizado', Documento, NULL)) AS finalizados,
      COUNT(DISTINCT IF({des}, Documento, NULL)) AS desertores,
      COUNT(DISTINCT IF({est} = 'matrícula no exitosa', Documento, NULL)) AS matricula_no_exitosa,
      COUNTIF({imp}) AS insc_impactadas,
      COUNTIF({ret}) AS insc_retenidas,
      COUNTIF({des}) AS insc_desertoras,
      COUNTIF({imp} AND {res} = 'aprobado') AS insc_aprobadas,
      COUNTIF({imp} AND {res} = 'reprobado') AS insc_reprobadas
    FROM base
    WHERE Fecha IS NOT NULL
    GROUP BY GROUPING SETS ((Fecha, Proyecto, Prog), (Fecha, Proyecto))
    """


def serie_seguimiento(impactado: set, retenido: set, desercion: set) -> str:
    """Foto mensual (APPEND, fecha = día 1 del mes) + foto diaria (DIARIO), en una sola tabla."""
    mensual = _serie_seguimiento(_t("Unificado_Seguimiento_APPEND"),
                                 "SAFE.PARSE_DATE('%Y-%m', SUBSTR(CAST(Fecha_Append AS STRING), 1, 7))",
                                 "mensual", impactado, retenido, desercion)
    diaria = _serie_seguimiento(_t("Seguimiento_DIARIO"), "Fecha_Foto", "diaria",
                                impactado, retenido, desercion)
    # Cada rama trae su propio WITH: van entre paréntesis para que BigQuery acepte el UNION.
    return f"({mensual})\nUNION ALL\n({diaria})\nORDER BY Fecha, Proyecto, Programa"


def serie_seguimiento_solo_mensual(impactado: set, retenido: set, desercion: set) -> str:
    """Por si la tabla diaria aún no existe (antes de la primera foto)."""
    return _serie_seguimiento(_t("Unificado_Seguimiento_APPEND"),
                              "SAFE.PARSE_DATE('%Y-%m', SUBSTR(CAST(Fecha_Append AS STRING), 1, 7))",
                              "mensual", impactado, retenido, desercion)


def _serie_empleabilidad(origen_sql: str, fecha_sql: str, etiqueta: str, contratado: set) -> str:
    con = f"LOWER(TRIM(Estado_contratacion)) IN ({_lista({e.lower() for e in contratado})})"
    return f"""
    SELECT
      '{etiqueta}' AS Origen, {fecha_sql} AS Fecha, Proyecto,
      COUNT(DISTINCT CAST(Documento AS STRING)) AS participantes,
      COUNT(DISTINCT IF({con}, CAST(Documento AS STRING), NULL)) AS contratados,
      COUNT(DISTINCT IF(LOWER(TRIM(Estado_contratacion)) = 'postulado', CAST(Documento AS STRING), NULL)) AS postulados,
      SUM(SAFE_CAST(Total_remisiones_postulaciones AS INT64)) AS postulaciones
    FROM {origen_sql}
    WHERE Documento IS NOT NULL
    GROUP BY Fecha, Proyecto
    """


def serie_empleabilidad(contratado: set, con_diaria: bool = True) -> str:
    mensual = _serie_empleabilidad(_t("Unificado_Empleabilidad_APPEND"),
                                   "SAFE.PARSE_DATE('%Y-%m', SUBSTR(CAST(Fecha_Append AS STRING), 1, 7))",
                                   "mensual", contratado)
    if not con_diaria:
        return mensual
    diaria = _serie_empleabilidad(_t("Empleabilidad_DIARIO"), "Fecha_Foto", "diaria", contratado)
    return f"({mensual})\nUNION ALL\n({diaria})"


def existe_tabla(tabla: str) -> str:
    return f"SELECT COUNT(*) AS n FROM `{DATASET}.INFORMATION_SCHEMA.TABLES` WHERE table_name = '{tabla}'"
