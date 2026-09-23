"""
Referencia: query SQL fuente de la pestaña LIFF Data.

Este archivo YA NO SE EJECUTA desde Python. Se deja como documentación
para quien mantenga el proyecto -- la query real la ejecuta un nodo
BigQuery -- Execute Query dentro de un workflow de n8n (Schedule Trigger
-> BigQuery -> Google Sheets Clear + Append), con credenciales que sí
tienen acceso al proyecto `potent-poetry-284019` (DSKU_CRM, DSKU_SIS,
DSGE_SIS, DVKU_SIS) -- ninguno de esos datasets tiene Service Account
propio, y por eso Streamlit no puede consultarlos en vivo (mismo
bloqueo, mismo proyecto, que `active_usage_hours` de IQ). El resultado se
lee vía utils/liff_crm_data.py::load_liff_crm() (gspread), apuntando al
sheet_id/worksheet que Christian configure en st.secrets["liff_crm"].

--------------------------------------------------------------------------
sept-2026 -- REEMPLAZO DE QUERY: Christian trajo una versión mucho más
completa (ver "QUERY_UNIFICADA_2026_09" abajo) que agrega el bloque CRM
(matriculados Y prematriculados, con datos de asesor/campaña/monto) al
bloque académico que ya existía. Decisión (Q1 del chat con Claude,
sept-2026): esta query REEMPLAZA a la anterior como fuente de la página
LIFF Data -- ya no se usa "QUERY_ANTERIOR_SOLO_SIS" (se deja más abajo
solo como referencia histórica, por si hace falta comparar).

Cambios de grano importantes para quien lea números de esta hoja:
  - Antes: 1 fila = 1 módulo/materia, SOLO estudiantes con match en el SIS
    y grupo iniciado >= 2026-08-01 (el filtro de fecha del SIS).
  - Ahora: 1 fila = 1 matriculado/prematriculado + materia. Prematriculados
    y matriculados SIN usuario SIS aparecen con 1 sola fila y los campos
    académicos en NULL -- no se pueden confundir con "0 materias
    cursadas", son poblaciones que el reporte viejo ni siquiera veía.
  - ALERTA_SIN_USUARIO_SIS = 'SI' marca matriculados (no prematriculados)
    sin usuario SIS asociado -- posible cédula mal digitada en CRM o SIS,
    o usuario que aún no se ha creado en el SIS. Panel de calidad de
    datos en la página, no se descarta ni se oculta.
--------------------------------------------------------------------------

QUERY ACTIVA (QUERY_UNIFICADA_2026_09) -- la ejecuta el nodo BigQuery de n8n:
--------------------------------------------------------------------------
-- =====================================================================================================
-- REPORTE UNIFICADO: Matriculados / Prematriculados (CRM) + Estado académico detallado por materia (SIS)
-- =====================================================================================================
-- GRANO: 1 fila por matriculado/prematriculado + materia cursada en el SIS.
--   - Prematriculados: 1 sola fila, con todos los campos académicos en NULL (no tienen curso todavía).
--   - Matriculados con usuario SIS: tantas filas como materias tengan registradas en el SIS (filtradas
--     por el mismo criterio de fecha de inicio de grupo >= 2026-08-01 y programas que empiezan con 'T'
--     que traía la consulta original del SIS, sin modificar).
--   - Matriculados SIN match de usuario en el SIS (posible cédula mal digitada, o usuario aún no
--     creado): 1 sola fila, campos académicos en NULL, y ALERTA_SIN_USUARIO_SIS = 'SI'.
--
-- DECISIONES CONFIRMADAS CON CHRISTIAN:
--   1. Detalle por materia (no resumen agregado por persona).
--   2. Se dejó intacto el filtro de fecha del SIS (>= 2026-08-01). Importante: un matriculado con
--      usuario SIS pero cuyo grupo inició ANTES de esa fecha también saldrá con info académica en
--      NULL -- eso es esperado por el filtro, no significa que le falte usuario SIS. Por eso la
--      alerta de abajo NO se basa en "sin materias", sino específicamente en "sin usuario SIS".
--   3. ALERTA_SIN_USUARIO_SIS: se activa solo para MATRICULADOS (no prematriculados) sin usuario SIS
--      asociado. LEAD_STATUS_DATA_NAME LIKE '%matriculado%' también hace match con "prematriculado"
--      (la palabra la contiene), así que se agregó la columna TIPO_MATRICULA para separarlos bien.
--   4. Entregado como consulta para crear una VIEW en BigQuery (no se conectó a Sheets todavía).
--
-- SIMPLIFICACIONES editoriales sobre el SELECT final del SIS (avisa si las necesitas de vuelta):
--   - Se quitaron del resultado final DOC_TYPE_NAME, DOC_TYPE_DESCRIPTION, PROFILE_DOC_TYPE y USER_ID
--     (quedan disponibles dentro del CTE Academico_Detalle si los necesitas, ya que DOCTYPE y
--     _POBLACION se calculan a partir de ellos).
--   - PROGRAM_DATA_NAME (CRM) y PROGRAMA (SIS) se renombraron a PROGRAMA_CRM y PROGRAMA_SIS para que
--     puedas comparar si coinciden (a veces no son exactamente el mismo texto).
-- =====================================================================================================

WITH

-- ---------------------------------------------------------------------------------------------------
-- BLOQUE CRM (matriculados y prematriculados) -- igual al original, sin cambios de lógica
-- ---------------------------------------------------------------------------------------------------

Usuarios_Agrupados AS (
    SELECT
        TRIM(CAST(SU.PROFILE_DOC_NUMBER AS STRING)) AS Cedula,
        SU.USERNAME,
        SU.INCREMENTAL_USER_CODE,
        SU._ID AS INTERNAL_USER_ID,
        DATE(SU.LAST_LOGIN, 'America/Bogota') AS Ultima_Fecha_Ingreso_DATE,
        TIME(SU.LAST_LOGIN, 'America/Bogota') AS Ultima_Fecha_Ingreso_HOUR,
        SU.LAST_LOGIN,
        COUNT(SL._ID) AS Cantidad_Asistencias,
        CASE
            WHEN COUNT(SL._ID) > 0 OR SU.LAST_LOGIN IS NOT NULL THEN 'SI'
            ELSE 'NO'
        END AS Tiene_Ingreso
    FROM
        `potent-poetry-284019.DSKU_SIS.EKU100010_user` AS SU
    LEFT JOIN
        `potent-poetry-284019.DSKU_SIS.EKU101005_log_access` AS SL ON SU._ID = SL.USER
    GROUP BY
        TRIM(CAST(SU.PROFILE_DOC_NUMBER AS STRING)),
        SU.USERNAME,
        SU.INCREMENTAL_USER_CODE,
        SU._ID,
        SU.LAST_LOGIN
),

Usuarios_Unicos AS (
    SELECT * FROM (
        SELECT
            Cedula,
            USERNAME,
            INCREMENTAL_USER_CODE,
            INTERNAL_USER_ID,
            Ultima_Fecha_Ingreso_DATE,
            Ultima_Fecha_Ingreso_HOUR,
            Cantidad_Asistencias,
            Tiene_Ingreso,
            ROW_NUMBER() OVER (
                PARTITION BY Cedula
                ORDER BY CASE WHEN LAST_LOGIN IS NOT NULL THEN 1 ELSE 2 END ASC, LAST_LOGIN DESC, INTERNAL_USER_ID DESC
            ) AS posicion
        FROM Usuarios_Agrupados
    )
    WHERE posicion = 1 AND Cedula IS NOT NULL AND Cedula != ''
),

Enrollment_Unico AS (
    SELECT
        LEAD_ID,
        MAX(DURATION_START_DATE) AS DURATION_START_DATE
    FROM
        `potent-poetry-284019.DSKU_CRM.EKU200020_enrollment`
    WHERE
        LEAD_ID IS NOT NULL
    GROUP BY
        LEAD_ID
),

Leads_Unificados AS (
    SELECT
        DATE(L.CREATED_AT, 'America/Bogota') AS CREATED_AT_DATE,
        TIME(L.CREATED_AT, 'America/Bogota') AS CREATED_AT_HOUR,
        L.CONTACT_DATA_FULL_NAME,
        SAFE_CAST(L.INCREMENTAL_LEAD_CODE AS INT64) AS INCREMENTAL_LEAD_CODE,
        SAFE_CAST(L.CONTACT_DATA_INCREMENTAL_CONTACT_CODE AS INT64) AS CONTACT_DATA_INCREMENTAL_CONTACT_CODE,
        L.CONTACT_DATA_MOBILE_PHONE,
        L.CONTACT_DATA_PHONE,
        L.CONTACT_DATA_EMAIL,
        L.CAMPAIGN_DATA_NAME,
        L.LEAD_STATUS_DATA_NAME,
        L.CONTACT_DATA_ADNETWORK_NAME,
        L.ENROLLMENT_DATA_FIRST_PAY,
        COALESCE(
            DATE(L.ENROLLMENT_DATA_DATE_FIRST_PAY, 'America/Bogota'),
            DATE(L.ENROLLMENT_DATA_DATE_ENROLLED, 'America/Bogota')
        ) AS ENROLLMENT_DATA_DATE_FIRST_PAY_DATE,
        TIME(L.ENROLLMENT_DATA_DATE_FIRST_PAY, 'America/Bogota') AS ENROLLMENT_DATA_DATE_FIRST_PAY_HOUR,
        DATE(L.ENROLLMENT_DATA_DATE_ENROLLED, 'America/Bogota') AS ENROLLMENT_DATA_DATE_ENROLLED_DATE,
        TIME(L.ENROLLMENT_DATA_DATE_ENROLLED, 'America/Bogota') AS ENROLLMENT_DATA_DATE_ENROLLED_HOUR,
        SAFE_CAST(L.ENROLLMENT_DATA_AMOUNT_PAYED AS INT64) AS ENROLLMENT_DATA_AMOUNT_PAYED,
        SAFE_CAST(L.ENROLLMENT_DATA_AMOUNT_CONTRACT AS INT64) AS ENROLLMENT_DATA_AMOUNT_CONTRACT,
        L.CONTACT_DATA_DOCUMENT_ID,
        REPLACE(
            TRIM(CONCAT(COALESCE(L.SALES_ADVISOR_DATA_FIRST_NAME, ''), ' ', COALESCE(L.SALES_ADVISOR_DATA_LAST_NAME, ''))),
            'Juan_David',
            'Juan David'
        ) AS SALES_ADVISOR_FULL_NAME,
        L.PROGRAM_DATA_NAME,
        COALESCE(U.USERNAME, 'No Registrado') AS USERNAME,
        U.INCREMENTAL_USER_CODE,
        U.INTERNAL_USER_ID,
        U.Ultima_Fecha_Ingreso_DATE,
        U.Ultima_Fecha_Ingreso_HOUR,
        COALESCE(U.Cantidad_Asistencias, 0) AS Cantidad_Asistencias,
        COALESCE(U.Tiene_Ingreso, 'NO') AS Tiene_Ingreso,
        C.ADDRESS,
        C.NEIGHBORHOOD,
        C.GENDER,
        C.LOCALITY,
        C.DOCUMENT_TYPE,
        C.SOCIOECONOMIC_LEVEL,
        DATE(C.BIRTHDAY, 'America/Bogota') AS BIRTHDAY,
        DATE_DIFF(CURRENT_DATE('America/Bogota'), DATE(C.BIRTHDAY, 'America/Bogota'), YEAR) -
            IF(EXTRACT(MONTH FROM CURRENT_DATE('America/Bogota')) < EXTRACT(MONTH FROM DATE(C.BIRTHDAY, 'America/Bogota'))
            OR (EXTRACT(MONTH FROM CURRENT_DATE('America/Bogota')) = EXTRACT(MONTH FROM DATE(C.BIRTHDAY, 'America/Bogota'))
                AND EXTRACT(DAY FROM CURRENT_DATE('America/Bogota')) < EXTRACT(DAY FROM DATE(C.BIRTHDAY, 'America/Bogota'))), 1, 0) AS EDAD_EXACTA,
        DATE(E.DURATION_START_DATE, 'America/Bogota') AS DURATION_START_DATE,
        ROW_NUMBER() OVER (
            PARTITION BY SAFE_CAST(L.INCREMENTAL_LEAD_CODE AS INT64)
            ORDER BY
                CASE WHEN LOWER(L.LEAD_STATUS_DATA_NAME) LIKE '%matriculado%' THEN 1 ELSE 2 END ASC,
                CASE WHEN L.ENROLLMENT_DATA_AMOUNT_PAYED IS NOT NULL THEN 1 ELSE 2 END ASC,
                L.ENROLLMENT_DATA_AMOUNT_PAYED DESC,
                L.CREATED_AT DESC
        ) AS fila_duplicada
    FROM
        `potent-poetry-284019.DSKU_CRM.EKU200060_lead` AS L
    LEFT JOIN
        Enrollment_Unico AS E ON L._ID = E.LEAD_ID
    LEFT JOIN
        Usuarios_Unicos AS U ON TRIM(CAST(L.CONTACT_DATA_DOCUMENT_ID AS STRING)) = U.Cedula
    LEFT JOIN
        `potent-poetry-284019.DSKU_CRM.EKU200080_contact` AS C ON TRIM(CAST(L.CONTACT_DATA_DOCUMENT_ID AS STRING)) = TRIM(CAST(C.DOCUMENT_ID AS STRING))
    WHERE
        LOWER(CAST(L.ENROLLMENT_DATA_FIRST_PAY AS STRING)) IN ('true', '1')
        AND COALESCE(
            DATE(L.ENROLLMENT_DATA_DATE_FIRST_PAY, 'America/Bogota'),
            DATE(L.ENROLLMENT_DATA_DATE_ENROLLED, 'America/Bogota')
        ) >= '2025-12-06'
        AND (
            LOWER(L.LEAD_STATUS_DATA_NAME) LIKE '%matriculado%'
            OR LOWER(L.LEAD_STATUS_DATA_NAME) LIKE '%pre%matriculado%'
            OR L.LEAD_STATUS_DATA_NAME IS NULL
        )
        AND L.PROGRAM_DATA_NAME IN (
            'Inactivo T.L. en Auxiliar de Mercadeo y Venta',
            'T.L en Auxiliar de Mercadeo y Ventas',
            'T.L en Procesamiento y Digitación de Datos',
            'T.L. en Auxiliar Administrativo',
            'T.L. en Contabilidad y Finanzas',
            'Técnico Laboral en Auxiliar Administrativo',
            'Técnico Laboral en Auxiliar de Mercadeo y Ventas',
            'Técnico laboral en procesamiento de datos',
            'Técnico laboral en servicios turísticos y hoteleros'
        )
        AND REPLACE(
            TRIM(CONCAT(COALESCE(L.SALES_ADVISOR_DATA_FIRST_NAME, ''), ' ', COALESCE(L.SALES_ADVISOR_DATA_LAST_NAME, ''))),
            'Juan_David',
            'Juan David'
        ) NOT IN (
            'Diana Pedraza',
            'Esteban Corredor',
            'Estefany Sofía Gómez Agredo',
            'Gestor JOVENES A LA E',
            'Lina Maria Macareno Rivas',
            'Nataly Concha',
            'Zamara Perez'
        )
),

CRM_Final AS (
    SELECT
        CREATED_AT_DATE,
        CREATED_AT_HOUR,
        CONTACT_DATA_FULL_NAME,
        INCREMENTAL_LEAD_CODE,
        CONTACT_DATA_INCREMENTAL_CONTACT_CODE,
        CONTACT_DATA_MOBILE_PHONE,
        CONTACT_DATA_PHONE,
        CONTACT_DATA_EMAIL,
        LEAD_STATUS_DATA_NAME,
        -- MATRICULADO vs PREMATRICULADO explícito: LIKE '%matriculado%' también matchea
        -- "prematriculado", así que sin esto no se pueden separar de forma confiable.
        CASE
            WHEN LOWER(LEAD_STATUS_DATA_NAME) LIKE '%pre%matriculado%' THEN 'PREMATRICULADO'
            WHEN LOWER(LEAD_STATUS_DATA_NAME) LIKE '%matriculado%' THEN 'MATRICULADO'
            ELSE 'SIN_ESTADO'
        END AS TIPO_MATRICULA,
        CONTACT_DATA_ADNETWORK_NAME,
        CAMPAIGN_DATA_NAME,
        ENROLLMENT_DATA_FIRST_PAY,
        ENROLLMENT_DATA_DATE_FIRST_PAY_DATE,
        ENROLLMENT_DATA_DATE_FIRST_PAY_HOUR,
        ENROLLMENT_DATA_DATE_ENROLLED_DATE,
        ENROLLMENT_DATA_DATE_ENROLLED_HOUR,
        ENROLLMENT_DATA_AMOUNT_PAYED,
        ENROLLMENT_DATA_AMOUNT_CONTRACT,
        DURATION_START_DATE,
        CONTACT_DATA_DOCUMENT_ID,
        SALES_ADVISOR_FULL_NAME,
        PROGRAM_DATA_NAME,
        USERNAME,
        INCREMENTAL_USER_CODE,
        INTERNAL_USER_ID,
        Ultima_Fecha_Ingreso_DATE,
        Ultima_Fecha_Ingreso_HOUR,
        Cantidad_Asistencias,
        Tiene_Ingreso,
        ADDRESS,
        NEIGHBORHOOD,
        GENDER,
        LOCALITY,
        DOCUMENT_TYPE,
        SOCIOECONOMIC_LEVEL,
        BIRTHDAY,
        EDAD_EXACTA
    FROM Leads_Unificados
    WHERE fila_duplicada = 1
    -- AND DOCUMENT_TYPE = 'ppt'   -- (se deja igual que el original, comentado)
),

-- ---------------------------------------------------------------------------------------------------
-- BLOQUE SIS (estado académico detallado por materia) -- igual al original, sin cambios de lógica
-- ---------------------------------------------------------------------------------------------------

ACADEMIC_STATUS AS (
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
),

Academico_Detalle AS (
  SELECT DISTINCT
    CASE
      WHEN COALESCE(E100900.DESCRIPTION, E100010.PROFILE_DOC_TYPE) IN
        ('PPT Permiso por protección temporal', 'PS Pasaporte',
         'CE Cédula de Extranjería', 'DE Documento de identidad extranjera')
        THEN 'extranjero'
      ELSE 'nacional'
    END AS _POBLACION,
    COALESCE(E100900.DESCRIPTION, E100010.PROFILE_DOC_TYPE) AS DOCTYPE,
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
    AND DATE(primera_fecha.primera_fecha_inicio) >= DATE('2026-08-01')
    -- ^ Filtro de fecha del SIS: se deja igual que el original, confirmado con Christian.
)

-- ---------------------------------------------------------------------------------------------------
-- REPORTE FINAL UNIFICADO
-- ---------------------------------------------------------------------------------------------------

SELECT
    -- ==== Datos del CRM (matriculado / prematriculado) ====
    CRM_Final.CREATED_AT_DATE,
    CRM_Final.CREATED_AT_HOUR,
    CRM_Final.CONTACT_DATA_FULL_NAME,
    CRM_Final.INCREMENTAL_LEAD_CODE,
    CRM_Final.CONTACT_DATA_INCREMENTAL_CONTACT_CODE,
    CRM_Final.CONTACT_DATA_MOBILE_PHONE,
    CRM_Final.CONTACT_DATA_PHONE,
    CRM_Final.CONTACT_DATA_EMAIL,
    CRM_Final.LEAD_STATUS_DATA_NAME,
    CRM_Final.TIPO_MATRICULA,
    CRM_Final.CONTACT_DATA_ADNETWORK_NAME,
    CRM_Final.CAMPAIGN_DATA_NAME,
    CRM_Final.ENROLLMENT_DATA_FIRST_PAY,
    CRM_Final.ENROLLMENT_DATA_DATE_FIRST_PAY_DATE,
    CRM_Final.ENROLLMENT_DATA_DATE_FIRST_PAY_HOUR,
    CRM_Final.ENROLLMENT_DATA_DATE_ENROLLED_DATE,
    CRM_Final.ENROLLMENT_DATA_DATE_ENROLLED_HOUR,
    CRM_Final.ENROLLMENT_DATA_AMOUNT_PAYED,
    CRM_Final.ENROLLMENT_DATA_AMOUNT_CONTRACT,
    CRM_Final.DURATION_START_DATE,
    CRM_Final.CONTACT_DATA_DOCUMENT_ID,
    CRM_Final.SALES_ADVISOR_FULL_NAME,
    CRM_Final.PROGRAM_DATA_NAME AS PROGRAMA_CRM,
    CRM_Final.USERNAME,
    CRM_Final.INCREMENTAL_USER_CODE,
    CRM_Final.INTERNAL_USER_ID,
    CRM_Final.Ultima_Fecha_Ingreso_DATE,
    CRM_Final.Ultima_Fecha_Ingreso_HOUR,
    CRM_Final.Cantidad_Asistencias,
    CRM_Final.Tiene_Ingreso,
    CRM_Final.ADDRESS,
    CRM_Final.NEIGHBORHOOD,
    CRM_Final.GENDER,
    CRM_Final.LOCALITY,
    CRM_Final.DOCUMENT_TYPE,
    CRM_Final.SOCIOECONOMIC_LEVEL,
    CRM_Final.BIRTHDAY,
    CRM_Final.EDAD_EXACTA,

    -- Matriculado (no prematriculado) sin usuario SIS asociado: posible cédula mal digitada
    -- en alguno de los dos sistemas, o usuario que aún no ha sido creado en el SIS.
    IF(CRM_Final.TIPO_MATRICULA = 'MATRICULADO' AND CRM_Final.INCREMENTAL_USER_CODE IS NULL, 'SI', 'NO')
        AS ALERTA_SIN_USUARIO_SIS,

    -- ==== Estado académico detallado (SIS) — NULL si es prematriculado o no tiene match ====
    Academico_Detalle._POBLACION,
    Academico_Detalle.DOCTYPE,
    Academico_Detalle.NOMBRE AS NOMBRE_SIS,
    Academico_Detalle.DOCUMENTO AS DOCUMENTO_SIS,
    Academico_Detalle.PROGRAMA AS PROGRAMA_SIS,
    Academico_Detalle.CARRIL,
    Academico_Detalle.GRUPO,
    Academico_Detalle.FECHA_INICIO_GRUPO,
    Academico_Detalle.FECHA_FIN_GRUPO,
    Academico_Detalle.NOTA,
    Academico_Detalle.ESTADO_PUBLICACION,
    Academico_Detalle.ESTADO_APROBACION,
    Academico_Detalle.PROGRESO,
    Academico_Detalle.GROUP_ID,
    Academico_Detalle.PROGRAM_ID,
    Academico_Detalle.ESTADO AS ESTADO_ACADEMICO

FROM CRM_Final
LEFT JOIN Academico_Detalle
    ON CRM_Final.INCREMENTAL_USER_CODE = Academico_Detalle.ID_SIS

--WHERE CRM_Final.DOCUMENT_TYPE = 'ppt'

ORDER BY
    CRM_Final.TIPO_MATRICULA,
    CRM_Final.CONTACT_DATA_FULL_NAME,
    Academico_Detalle.FECHA_INICIO_GRUPO DESC;
--------------------------------------------------------------------------


-- =====================================================================================================
-- QUERY_ANTERIOR_SOLO_SIS -- REEMPLAZADA sept-2026, se deja solo de referencia histórica.
-- No se usa desde ningún workflow activo. NO editar esta sección.
-- =====================================================================================================

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
