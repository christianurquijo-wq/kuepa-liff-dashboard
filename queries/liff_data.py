"""
Referencia: query SQL fuente de la pestaña LIFF Data.

Este archivo YA NO SE EJECUTA desde Python. Se deja como documentación
para quien mantenga el proyecto -- la query real la ejecuta un nodo
BigQuery -- Execute Query dentro de un workflow de n8n (Schedule Trigger
-> BigQuery -> Google Sheets Clear + Append), con credenciales que sí
tienen acceso a DSGE_SIS. El resultado se escribe como valores planos en
la pestaña "LIF_Data_Export" del spreadsheet
1objyGOm_rGMFnQCw7Xyx5rUHhOXWtm2gfUvH02saU34, y Streamlit solo lee esa
pestaña (utils/sheets.py, vía gspread).

Por qué no vive en BigQuery vía el Service Account de Streamlit: la query
necesita DSGE_SIS.EGE100900_drop_down_list (catálogo de tipos de
documento), un dataset del proyecto central `potent-poetry-284019` que no
tiene Service Accounts y que, por política, no se puede duplicar dentro
de BigQuery (tampoco conviene: son catálogos de referencia que sí reciben
registros nuevos).

Nota histórica: antes de resolverlo con n8n se intentó un Connected Sheet
de BigQuery ("Consulta_LIF") + fórmula FILTER() y, después, un extracto
manual -- ninguno funcionó, porque una hoja conectada a BigQuery es de
tipo DATA_SOURCE y ni la API de Sheets ni la mayoría de funciones de
Sheets pueden leer su rango directamente. Ver utils/sheets.py para el
detalle completo.

Nota sobre EGE100810_business_status_category: el JOIN a esa tabla (dentro
de ACADEMIC_STATUS, para traer "category") se eliminó de la query original
-- nunca se usaba en el SELECT final de esta pestaña (ESTADO viene de
business_status, no de category). Código heredado sin uso real.

--------------------------------------------------------------------------
WITH ACADEMIC_STATUS AS (
  SELECT
    E100010.INCREMENTAL_USER_CODE AS incremental,
    COALESCE(E100210P.NAME, E100210.NAME) AS business_status
  FROM `potent-poetry-284019.DSKU_SIS.EKU100010_user` AS E100010
  INNER JOIN `potent-poetry-284019.DSKU_SIS.EKU100012_programs` AS E100012
    ON E100010._ID = E100012.__USER
  INNER JOIN `potent-poetry-284019.DSKU_SIS.EKU100100_structure` AS E100100
    ON E100012.STRUCTURE = E100100._ID
  INNER JOIN `potent-poetry-284019.DSKU_SIS.EKU100013_business_statuses` AS E100013
    ON E100012._ID = E100013.__PROGRAMS
  INNER JOIN `potent-poetry-284019.DSKU_SIS.EKU100210_business_status` AS E100210
    ON E100013.BUSINESS_STATUS = E100210._ID
  LEFT JOIN `potent-poetry-284019.DSKU_SIS.EKU100210_business_status` AS E100210P
    ON E100210.PARENT = E100210P._ID
  WHERE E100012.IS_CURRENT = TRUE
    AND E100010.DELETED IS NOT TRUE
),

FECHAS_GRUPO_UNICO AS (
  SELECT
    user_incremental,
    group_id,
    MAX(start_date) AS start_date,
    MAX(end_date) AS end_date
  FROM `potent-poetry-284019.DVKU_SIS.VKU10_student_all_grades`
  GROUP BY user_incremental, group_id
),

FECHA_MIN_ESTUDIANTE AS (
  SELECT
    user_incremental,
    MIN(start_date) AS primera_fecha_inicio
  FROM FECHAS_GRUPO_UNICO
  GROUP BY user_incremental
)

SELECT DISTINCT
  CASE
    WHEN COALESCE(E100900.DESCRIPTION, E100010.PROFILE_DOC_TYPE) IN
      ('PPT Permiso por protección temporal', 'PS Pasaporte',
       'CE Cédula de Extranjería', 'DE Documento de identidad extranjera')
      THEN 'extranjero'
    ELSE 'nacional'
  END AS _POBLACION,
  E100010.PROFILE_DOC_TYPE,
  E100900.NAME AS DOC_TYPE_NAME,
  E100900.DESCRIPTION AS DOC_TYPE_DESCRIPTION,
  COALESCE(E100900.DESCRIPTION, E100010.PROFILE_DOC_TYPE) AS DOCTYPE,
  E100400.USER_ID AS USER_ID,
  E100010.INCREMENTAL_USER_CODE AS ID_SIS,
  E100010.PROFILE_FULL_NAME AS NOMBRE,
  E100010.PROFILE_DOC_NUMBER AS DOCUMENTO,
  A100100.name AS PROGRAMA,
  UPPER(TRIM(PARENT_CARRIL.NAME)) AS CARRIL,
  E100100.name AS GRUPO,
  FORMAT_DATE('%d/%m/%Y', DATE(TIMESTAMP(fechas_grupo.start_date))) AS FECHA_INICIO_GRUPO,
  FORMAT_DATE('%d/%m/%Y', DATE(TIMESTAMP(fechas_grupo.end_date))) AS FECHA_FIN_GRUPO,
  COALESCE(SAFE_CAST(E100401.FINAL_NOTE_VALUE AS FLOAT64), 0) AS NOTA,
  E100401.FINAL_NOTE_PUBLISHED AS ESTADO_PUBLICACION,
  E100401.FINAL_NOTE_APPROVE AS ESTADO_APROBACION,
  E100201.COMPLETED_STATUS AS PROGRESO,
  E100100._ID AS GROUP_ID,
  A100100._id AS PROGRAM_ID,
  ACADEMIC_STATUS.business_status AS ESTADO

FROM `potent-poetry-284019.DSKU_SIS.EKU100401_subjects` AS E100401
  LEFT JOIN `potent-poetry-284019.DSKU_SIS.EKU100400_centralize_final_note` AS E100400
    ON E100401.__CENTRALIZEFINALNOTES = E100400._ID
  LEFT JOIN `potent-poetry-284019.DSKU_SIS.EKU100010_user` AS E100010
    ON E100010._id = E100400.USER_ID

  LEFT JOIN `potent-poetry-284019.DSGE_SIS.EGE100900_drop_down_list` E100900
    ON E100900._ID = E100010.PROFILE_DOC_TYPE

  LEFT JOIN `potent-poetry-284019.DSKU_SIS.EKU100415_subject` AS E100415
    ON E100415._ID = E100401.SUBJECT_ID
  LEFT JOIN `potent-poetry-284019.DSKU_SIS.EKU100200_user_statistic` AS E100200
    ON E100200.USER = E100010._id AND E100200.STRUCTURE = E100401.STRUCTURE_ID
  LEFT JOIN `potent-poetry-284019.DSKU_SIS.EKU100201_statistics` AS E100201
    ON E100201.ACADEMIC_COMPONENT = E100415.ACADEMIC_COMPONENT_ID AND E100200._ID = E100201.__MODEL
  LEFT JOIN `potent-poetry-284019.DSKU_SIS.EKU100405_pensum_level` AS E100405
    ON E100405._ID = E100400.LEVEL_ID
  LEFT JOIN `potent-poetry-284019.DSKU_SIS.EKU100100_structure` AS E100100
    ON E100100._id = E100401.STRUCTURE_ID
  LEFT JOIN `potent-poetry-284019.DSKU_SIS.EKU100100_structure` AS PARENT_CARRIL
    ON PARENT_CARRIL._ID = E100100.PARENT
  LEFT JOIN `potent-poetry-284019.DSKU_SIS.EKU100100_structure` AS A100100
    ON A100100._id = E100400.STRUCTURE_ID

  LEFT JOIN ACADEMIC_STATUS
    ON E100010.INCREMENTAL_USER_CODE = ACADEMIC_STATUS.incremental

  LEFT JOIN FECHAS_GRUPO_UNICO AS fechas_grupo
    ON fechas_grupo.user_incremental = E100010.INCREMENTAL_USER_CODE
    AND fechas_grupo.group_id = E100100._ID

  LEFT JOIN FECHA_MIN_ESTUDIANTE AS primera_fecha
    ON primera_fecha.user_incremental = E100010.INCREMENTAL_USER_CODE

WHERE
  E100010.DELETED IS NOT TRUE
  AND COALESCE(E100900.DESCRIPTION, E100010.PROFILE_DOC_TYPE) IS NOT NULL
  AND REGEXP_EXTRACT(A100100.name, r'^.') = 'T'
  AND primera_fecha.primera_fecha_inicio IS NOT NULL
  AND DATE(primera_fecha.primera_fecha_inicio) >= DATE('2026-08-01')  -- <- fecha de corte de la cohorte

ORDER BY
  E100010.INCREMENTAL_USER_CODE DESC,
  PARSE_DATE('%d/%m/%Y', FECHA_INICIO_GRUPO) DESC
--------------------------------------------------------------------------
"""
