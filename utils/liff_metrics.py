"""
Reglas de negocio + agregaciones para la pestaña LIFF Data.

Separado de pages/1_LIFF_Data.py a propósito: aquí vive la lógica (fácil
de testear/validar con datos reales), la página solo la llama y dibuja.

Reglas confirmadas con Christian (2026-09) -- si algún número no cuadra
contra el dashboard viejo de Looker, empieza a revisar por aquí:

1. % Retención = estudiantes cuyo ESTADO NO indica retiro/deserción
   explícita, sobre el total de estudiantes. Ver _ESTADOS_NO_RETENIDO
   abajo -- no tenemos el catálogo completo de valores de ESTADO, así que
   es una lista de palabras clave ajustable, no una lista cerrada.
2. Estado del módulo:
   - "Cursado"   si ESTADO_PUBLICACION = TRUE
   - "En Curso"  si no está publicada y FECHA_INICIO_GRUPO <= hoy
   - "Próximo"   si no está publicada y FECHA_INICIO_GRUPO > hoy (o no hay fecha)
3. Aprobación de módulos: SOLO sobre módulos con nota publicada.
   - "Aprobado" / "No Aprobado" según ESTADO_APROBACION
   - el resto es "Pendiente de Nota" (no entra en el % de aprobación)
4. Nota promedio: SOLO sobre módulos con nota publicada (los no
   publicados llegan con NOTA=0 por el COALESCE de la query en BigQuery,
   incluirlos arrastraría el promedio hacia 0).
   BUG corregido oct-2026: NOTA llega como texto con coma decimal
   ("4,6") -- to_float() no la reconocía y cada nota con coma caía
   silenciosamente en 0.0, arrastrando el promedio real (~3.4) a ~0.3.
   Ver to_float() más abajo.
5. Corte de técnicos (oct-2026, confirmado con Christian, FIJO -- sin
   toggle en la página): solo se analizan registros de estudiantes que
   ingresaron a los programas técnicos desde el 1 de agosto de 2026 en
   adelante. Dos variantes porque no todas las filas tienen la misma
   fecha disponible -- ver FECHA_CORTE_TECNICOS y
   filtrar_corte_tecnicos_*() más abajo:
   - Bloque académico (post-enrich(), con match real SIS): se usa
     _FECHA_INICIO (FECHA_INICIO_GRUPO) -- fecha real de inicio de
     cursada en el programa técnico.
   - Bloque CRM/funnel (post-enrich_crm(), incluye prematriculados y
     matriculados sin usuario SIS): criterio HÍBRIDO, _FECHA_CORTE_REF --
     usa FECHA_INICIO_GRUPO cuando existe (quien ya tiene match
     académico), y solo cae a CREATED_AT_DATE cuando no existe
     (prematriculados y matriculados sin usuario SIS, que no tienen
     fecha de inicio de grupo -- viene vacía a propósito, ver
     utils/liff_crm_data.py). Así alguien cuyo lead se creó antes del
     corte pero cuyo grupo arrancó después SÍ entra al funnel, y solo se
     usa la fecha de creación del lead como respaldo cuando no hay otra
     forma de saber si cumple el criterio.
6. Monto recaudado (oct-2026): se quitó de la VISUAL en las 4 pestañas a
   pedido de Christian -- comparativo_kpis()/funnel_kpis() lo siguen
   calculando (otros consumidores podrían necesitarlo), pages/1_LIFF_Data.py
   simplemente ya no lo muestra en los _kpi_row().
7. Diferenciación Extranjero/Nacional (oct-2026): se extendió del
   Comparativo (única pestaña que ya la tenía) a Académico y a
   Satisfacción/Caracterización.
   - Académico: _POBLACION ya viene en `aca` (mismo enrich() de siempre),
     así que ext/nac particiona el total sin pérdida -- ver las nuevas
     estado_academico_pct_poblacion()/aprobacion_pct_poblacion()/
     nota_promedio_por_programa_poblacion() abajo, hermanas de
     modulos_por_estado_pct_comparativo() y
     academico_resumen_por_dimension_poblacion() que ya existían.
   - Satisfacción/Caracterización: estas 2 encuestas NO traen _POBLACION
     propia (son hojas CRM aparte) -- se cruza por documento contra el
     bloque académico (mismo corte de técnicos) para etiquetar cada fila
     encuestada. Quien no cruza (no contestó con el mismo documento, o no
     tiene match académico) queda "Sin clasificar" y se excluye de las
     comparativas ext/nac, no se inventa una población.
"""
from datetime import date

import pandas as pd

# Palabras clave (en minúsculas, comparación por substring) que indican
# que el estudiante YA NO está en el programa. Ajusta esta lista si el
# catálogo real de ESTADO (business_status) trae otras etiquetas de
# salida que no estén cubiertas aquí.
_ESTADOS_NO_RETENIDO = ("retir", "desert", "cancel", "anulad", "inactiv")

# Sin "_" al inicio a propósito -- pages/1_LIFF_Data.py las importa para
# armar las opciones de los selectbox de "Estado del módulo"/"Aprobación"
# (el clic-para-filtrar en esas 2 gráficas necesita la lista exacta de
# categorías, en el mismo orden que las gráficas).
ORDEN_ESTADO_MODULO = ["Cursado", "En Curso", "Próximo"]
ORDEN_APROBACION = ["Aprobado", "No Aprobado", "Pendiente de Nota"]

# Ver regla 5 arriba. Fecha FIJA a propósito -- no es "últimos N días", es
# un corte de calendario absoluto que Christian pidió explícitamente.
FECHA_CORTE_TECNICOS = pd.Timestamp(2026, 8, 1)


def filtrar_corte_tecnicos_academico(df: pd.DataFrame) -> pd.DataFrame:
    """Bloque académico (después de enrich(), con _FECHA_INICIO ya
    calculada) -- se queda solo con _FECHA_INICIO >= FECHA_CORTE_TECNICOS.
    Las filas sin fecha (_FECHA_INICIO NaT) se excluyen (no se puede
    confirmar que cumplan el criterio)."""
    if "_FECHA_INICIO" not in df.columns:
        return df
    return df[df["_FECHA_INICIO"] >= FECHA_CORTE_TECNICOS]


def filtrar_corte_tecnicos_funnel(df: pd.DataFrame) -> pd.DataFrame:
    """Bloque CRM/funnel (después de enrich_crm(), con _FECHA_CORTE_REF ya
    calculada) -- se queda solo con _FECHA_CORTE_REF >= FECHA_CORTE_TECNICOS.
    _FECHA_CORTE_REF es FECHA_INICIO_GRUPO cuando existe, si no
    CREATED_AT_DATE -- ver nota de la regla 5 arriba."""
    if "_FECHA_CORTE_REF" not in df.columns:
        return df
    return df[df["_FECHA_CORTE_REF"] >= FECHA_CORTE_TECNICOS]


def to_bool(value) -> bool:
    """Normaliza valores de Sheets/BigQuery a bool -- cubre True/False de
    Python, texto 'TRUE'/'FALSE' (o su versión en español), y 1/0."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    texto = str(value).strip().lower()
    return texto in {"true", "verdadero", "1", "si", "sí", "yes"}


def to_float(value, default: float = 0.0) -> float:
    """oct-2026: NOTA llega desde Sheets como texto con COMA decimal
    (formato es-CO, ej. "4,6") -- float("4,6") revienta ValueError y esto
    caía en `default` (0.0) SIN avisar. Con 2 dígitos antes de la coma en
    notas normales (0-5) el bug era casi invisible fila por fila, pero
    arrastraba el promedio publicado de ~3.4 real a ~0.3 (Christian lo
    detectó). Se normaliza coma -> punto antes de castear."""
    try:
        if value in (None, ""):
            return default
        if isinstance(value, str):
            value = value.strip().replace(",", ".")
        return float(value)
    except (TypeError, ValueError):
        return default


def es_retenido(estado) -> bool:
    """True salvo que el ESTADO contenga alguna palabra de _ESTADOS_NO_RETENIDO."""
    if not estado:
        return False
    estado_low = str(estado).strip().lower()
    return not any(kw in estado_low for kw in _ESTADOS_NO_RETENIDO)


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega las columnas derivadas (_NOTA_NUM, _PUBLICADA, _APROBADA,
    _FECHA_INICIO, _ESTADO_MODULO, _APROBACION, _RETENIDO) que usan todas
    las funciones de este módulo. No modifica el DataFrame original.
    """
    df = df.copy()
    df["_NOTA_NUM"] = df["NOTA"].apply(to_float)
    df["_PUBLICADA"] = df["ESTADO_PUBLICACION"].apply(to_bool)
    df["_APROBADA"] = df["ESTADO_APROBACION"].apply(to_bool)
    df["_FECHA_INICIO"] = pd.to_datetime(
        df["FECHA_INICIO_GRUPO"], format="%d/%m/%Y", errors="coerce"
    )

    hoy = pd.Timestamp(date.today())

    def _estado_modulo(row) -> str:
        if row["_PUBLICADA"]:
            return "Cursado"
        fecha = row["_FECHA_INICIO"]
        if pd.notna(fecha) and fecha <= hoy:
            return "En Curso"
        return "Próximo"

    df["_ESTADO_MODULO"] = df.apply(_estado_modulo, axis=1)

    def _aprobacion(row) -> str:
        if not row["_PUBLICADA"]:
            return "Pendiente de Nota"
        return "Aprobado" if row["_APROBADA"] else "No Aprobado"

    df["_APROBACION"] = df.apply(_aprobacion, axis=1)
    df["_RETENIDO"] = df["ESTADO"].apply(es_retenido)
    return df


def _por_estudiante(df: pd.DataFrame) -> pd.DataFrame:
    """
    Una fila por estudiante (ID_SIS). ESTADO y PROGRAMA son atributos del
    estudiante, no del módulo -- deberían repetirse igual en todas sus
    filas, así que tomar la primera es suficiente para KPIs a nivel
    estudiante (Estudiantes, Programas, % Retención, Estado Académico).
    """
    if df.empty:
        return df
    return df.sort_values("ID_SIS").groupby("ID_SIS", as_index=False).first()


def _counts_ordenado(series: pd.Series, orden: list) -> pd.DataFrame:
    """value_counts() pero forzando el orden y las categorías dadas (con
    0 si una categoría no aparece), para que las gráficas no se reordenen
    ni se les caiga una barra cuando el filtro deja esa categoría vacía."""
    counts = series.value_counts()
    return pd.DataFrame(
        {"categoria": orden, "cantidad": [int(counts.get(c, 0)) for c in orden]}
    )


def kpis_overview(df: pd.DataFrame) -> dict:
    """KPIs de la sección overview (una sola población, ya filtrada)."""
    estudiantes = _por_estudiante(df)
    total_estudiantes = len(estudiantes)
    retenidos = int(estudiantes["_RETENIDO"].sum()) if total_estudiantes else 0
    pct_retencion = (retenidos / total_estudiantes * 100) if total_estudiantes else 0.0

    publicados = df[df["_PUBLICADA"]]
    aprobados = int((publicados["_APROBACION"] == "Aprobado").sum())
    no_aprobados = int((publicados["_APROBACION"] == "No Aprobado").sum())
    total_calificados = aprobados + no_aprobados
    pct_aprobacion = (aprobados / total_calificados * 100) if total_calificados else 0.0
    nota_promedio = publicados["_NOTA_NUM"].mean() if len(publicados) else 0.0

    return {
        "estudiantes": total_estudiantes,
        "programas": estudiantes["PROGRAMA"].nunique() if total_estudiantes else 0,
        "pct_retencion": pct_retencion,
        "pct_aprobacion": pct_aprobacion,
        "nota_promedio": nota_promedio if pd.notna(nota_promedio) else 0.0,
        "modulos_cursados": int((df["_ESTADO_MODULO"] == "Cursado").sum()),
        "modulos_en_curso": int((df["_ESTADO_MODULO"] == "En Curso").sum()),
        "modulos_proximos": int((df["_ESTADO_MODULO"] == "Próximo").sum()),
        "total_modulos": len(df),
    }


def estado_academico_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Distribución de ESTADO, a nivel estudiante (no módulo)."""
    estudiantes = _por_estudiante(df)
    if estudiantes.empty:
        return pd.DataFrame({"estado": [], "cantidad": []})
    counts = estudiantes["ESTADO"].fillna("Sin estado").value_counts()
    return pd.DataFrame({"estado": counts.index, "cantidad": counts.values})


def estado_modulo_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Cursados / En Curso / Próximos, a nivel módulo."""
    return _counts_ordenado(df["_ESTADO_MODULO"], ORDEN_ESTADO_MODULO)


def aprobacion_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Aprobado / No Aprobado / Pendiente de Nota, a nivel módulo."""
    return _counts_ordenado(df["_APROBACION"], ORDEN_APROBACION)


def estudiantes_por_programa(df: pd.DataFrame) -> pd.DataFrame:
    estudiantes = _por_estudiante(df)
    if estudiantes.empty:
        return pd.DataFrame({"PROGRAMA": [], "estudiantes": []})
    out = estudiantes.groupby("PROGRAMA")["ID_SIS"].nunique().reset_index(name="estudiantes")
    return out.sort_values("estudiantes", ascending=False)


def nota_promedio_por_programa(df: pd.DataFrame) -> pd.DataFrame:
    """Nota promedio por programa -- solo módulos con nota publicada."""
    publicados = df[df["_PUBLICADA"]]
    if publicados.empty:
        return pd.DataFrame({"PROGRAMA": [], "nota_promedio": []})
    out = publicados.groupby("PROGRAMA")["_NOTA_NUM"].mean().reset_index(name="nota_promedio")
    return out.sort_values("nota_promedio", ascending=False)


def comparativo_kpis(df_ext: pd.DataFrame, df_nac: pd.DataFrame) -> dict:
    """KPIs de la sección comparativa -- siempre sobre el total de cada
    población (sin los filtros de programa/estado del overview salvo los
    que ya se aplicaron antes de separar por población -- ver
    pages/1_LIFF_Data.py)."""

    def _bloque(df: pd.DataFrame) -> dict:
        estudiantes = _por_estudiante(df)
        total_estudiantes = len(estudiantes)
        retenidos = int(estudiantes["_RETENIDO"].sum()) if total_estudiantes else 0
        pct_retencion = (retenidos / total_estudiantes * 100) if total_estudiantes else 0.0

        publicados = df[df["_PUBLICADA"]]
        aprobados = int((publicados["_APROBACION"] == "Aprobado").sum())
        no_aprobados = int((publicados["_APROBACION"] == "No Aprobado").sum())
        total_calificados = aprobados + no_aprobados
        pct_aprobacion = (aprobados / total_calificados * 100) if total_calificados else 0.0
        nota_promedio = publicados["_NOTA_NUM"].mean() if len(publicados) else 0.0

        # Monto recaudado -- viene del bloque CRM (ENROLLMENT_DATA_AMOUNT_PAYED),
        # que sigue presente en `aca` porque academico_de() solo filtra filas y
        # renombra 3 columnas, no descarta el resto del CRM. Se toma 1 vez por
        # estudiante (no por materia) para no sumarlo de más.
        monto = (
            estudiantes["ENROLLMENT_DATA_AMOUNT_PAYED"].sum()
            if "ENROLLMENT_DATA_AMOUNT_PAYED" in estudiantes.columns
            else 0.0
        )

        return {
            "estudiantes": total_estudiantes,
            "modulos": len(df),
            "pct_retencion": pct_retencion,
            "pct_aprobacion": pct_aprobacion,
            "nota_promedio": nota_promedio if pd.notna(nota_promedio) else 0.0,
            "monto_recaudado": float(monto) if pd.notna(monto) else 0.0,
        }

    return {"extranjero": _bloque(df_ext), "nacional": _bloque(df_nac)}


def academico_resumen_por_dimension_poblacion(
    df_ext: pd.DataFrame, df_nac: pd.DataFrame, columna: str, top: int = 12
) -> pd.DataFrame:
    """% de aprobación y estudiantes por `columna` (ej. PROGRAMA,
    SALES_ADVISOR_FULL_NAME), separado Extranjeros vs Nacionales -- para
    los cruces de la pestaña Comparativo. `top` limita a las categorías
    con más estudiantes en total (evita gráficas ilegibles con muchos
    asesores)."""
    filas = []
    for poblacion, df in (("Extranjeros", df_ext), ("Nacionales", df_nac)):
        if df.empty or columna not in df.columns:
            continue
        d = df.copy()
        d[columna] = d[columna].fillna("(sin dato)")
        for valor, g in d.groupby(columna, observed=True):
            publicadas = g[g["_PUBLICADA"]]
            aprobadas = int((publicadas["_APROBACION"] == "Aprobado").sum())
            total_calificadas = len(publicadas)
            filas.append(
                {
                    columna: valor,
                    "poblacion": poblacion,
                    "pct_aprobacion": (aprobadas / total_calificadas * 100) if total_calificadas else None,
                    "estudiantes": g["ID_SIS"].nunique() if "ID_SIS" in g.columns else len(g),
                }
            )
    out = pd.DataFrame(filas)
    if out.empty:
        return out
    top_valores = out.groupby(columna)["estudiantes"].sum().sort_values(ascending=False).head(top).index
    return out[out[columna].isin(top_valores)]


def tendencia_mensual_poblacion(df_ext: pd.DataFrame, df_nac: pd.DataFrame) -> pd.DataFrame:
    """Estudiantes distintos por mes de inicio de grupo (_FECHA_INICIO,
    de enrich()), Extranjeros vs Nacionales -- para ver si la composición
    cambia en el tiempo, no solo el acumulado."""
    partes = []
    for poblacion, df in (("Extranjeros", df_ext), ("Nacionales", df_nac)):
        if df.empty or "_FECHA_INICIO" not in df.columns:
            continue
        d = df.dropna(subset=["_FECHA_INICIO"])
        if d.empty:
            continue
        d = d.copy()
        d["_MES"] = d["_FECHA_INICIO"].dt.to_period("M").dt.to_timestamp()
        por_mes = d.groupby("_MES", observed=True)["ID_SIS"].nunique().reset_index(name="estudiantes")
        por_mes["poblacion"] = poblacion
        partes.append(por_mes)
    if not partes:
        return pd.DataFrame(columns=["_MES", "estudiantes", "poblacion"])
    return pd.concat(partes, ignore_index=True)


def modulos_por_estado_pct_comparativo(
    df_ext: pd.DataFrame, df_nac: pd.DataFrame
) -> pd.DataFrame:
    """
    Cursados/En Curso/Próximos como % DEL TOTAL DE CADA POBLACIÓN (los %
    de cada población suman ~100% por separado -- no es una comparación
    de volumen absoluto, es de composición).
    """
    filas = []
    for poblacion, df in (("Extranjeros", df_ext), ("Nacionales", df_nac)):
        total = len(df)
        counts = df["_ESTADO_MODULO"].value_counts()
        for categoria in ORDEN_ESTADO_MODULO:
            cantidad = int(counts.get(categoria, 0))
            pct = (cantidad / total * 100) if total else 0.0
            filas.append(
                {
                    "poblacion": poblacion,
                    "categoria": categoria,
                    "porcentaje": pct,
                    "cantidad": cantidad,
                }
            )
    return pd.DataFrame(filas)


def estado_academico_pct_poblacion(df_ext: pd.DataFrame, df_nac: pd.DataFrame) -> pd.DataFrame:
    """Distribución de ESTADO académico (a nivel estudiante, no módulo)
    como % del total de cada población -- hermana de
    modulos_por_estado_pct_comparativo() pero para estado_academico_counts()."""
    bloques = {}
    categorias: set = set()
    for poblacion, df in (("Extranjeros", df_ext), ("Nacionales", df_nac)):
        estudiantes = _por_estudiante(df)
        if estudiantes.empty:
            bloques[poblacion] = (pd.Series(dtype=int), 0)
            continue
        counts = estudiantes["ESTADO"].fillna("Sin estado").value_counts()
        bloques[poblacion] = (counts, len(estudiantes))
        categorias.update(counts.index.tolist())
    filas = []
    for poblacion, (counts, total) in bloques.items():
        for categoria in sorted(categorias):
            cantidad = int(counts.get(categoria, 0))
            pct = (cantidad / total * 100) if total else 0.0
            filas.append({"poblacion": poblacion, "estado": categoria, "porcentaje": pct, "cantidad": cantidad})
    return pd.DataFrame(filas)


def aprobacion_pct_poblacion(df_ext: pd.DataFrame, df_nac: pd.DataFrame) -> pd.DataFrame:
    """Aprobado/No Aprobado/Pendiente de Nota como % del total de módulos
    de cada población -- mismo criterio que aprobacion_counts() (sobre
    TODOS los módulos, no solo los publicados: "Pendiente de Nota" ya es
    una de las 3 categorías)."""
    filas = []
    for poblacion, df in (("Extranjeros", df_ext), ("Nacionales", df_nac)):
        total = len(df)
        counts = df["_APROBACION"].value_counts() if "_APROBACION" in df.columns else pd.Series(dtype=int)
        for categoria in ORDEN_APROBACION:
            cantidad = int(counts.get(categoria, 0))
            pct = (cantidad / total * 100) if total else 0.0
            filas.append({"poblacion": poblacion, "categoria": categoria, "porcentaje": pct, "cantidad": cantidad})
    return pd.DataFrame(filas)


def nota_promedio_por_programa_poblacion(df_ext: pd.DataFrame, df_nac: pd.DataFrame) -> pd.DataFrame:
    """Nota promedio por PROGRAMA (solo módulos con nota publicada),
    Extranjeros vs Nacionales -- hermana de nota_promedio_por_programa()."""
    partes = []
    for poblacion, df in (("Extranjeros", df_ext), ("Nacionales", df_nac)):
        if df.empty or "PROGRAMA" not in df.columns:
            continue
        publicados = df[df["_PUBLICADA"]]
        if publicados.empty:
            continue
        d = publicados.copy()
        d["PROGRAMA"] = d["PROGRAMA"].fillna("(sin dato)")
        prom = d.groupby("PROGRAMA", observed=True)["_NOTA_NUM"].mean().reset_index(name="nota_promedio")
        prom["poblacion"] = poblacion
        partes.append(prom)
    if not partes:
        return pd.DataFrame(columns=["PROGRAMA", "nota_promedio", "poblacion"])
    return pd.concat(partes, ignore_index=True)


# =============================================================================
# CRM + funnel de matrícula (sept-2026) -- consulta unificada CRM+SIS, ver
# utils/liff_crm_data.py::load_liff_crm() y queries/liff_data.py.
#
# Grano de esta fuente: 1 fila por matriculado/prematriculado + materia (o
# 1 sola fila si no tiene materias -- prematriculado, o matriculado sin
# usuario SIS). Por eso casi todo lo de abajo dedupe por
# INCREMENTAL_LEAD_CODE antes de contar personas -- sin eso, alguien con 5
# materias se contaría 5 veces en el funnel.
#
# El bloque académico (PROGRAMA_SIS/ESTADO_ACADEMICO/etc.) se reutiliza vía
# academico_de(), que lo renombra a los nombres que ya espera enrich() /
# kpis_overview() / etc. de arriba -- para no duplicar esa lógica ya
# validada con Christian.
# =============================================================================


def enrich_crm(df: pd.DataFrame) -> pd.DataFrame:
    """Tipa la salida de load_liff_crm() y agrega las columnas derivadas
    del bloque CRM. No toca el bloque académico -- eso lo hace
    academico_de() + enrich() por separado, solo sobre las filas con
    match real (evita mezclar NULLs de prematriculados en los cálculos
    académicos)."""
    df = df.copy()
    for col in ("ENROLLMENT_DATA_AMOUNT_PAYED", "ENROLLMENT_DATA_AMOUNT_CONTRACT", "EDAD_EXACTA", "Cantidad_Asistencias"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["_ES_MATRICULADO"] = df["TIPO_MATRICULA"] == "MATRICULADO"
    df["_ES_PREMATRICULADO"] = df["TIPO_MATRICULA"] == "PREMATRICULADO"
    df["_ALERTA_SIN_SIS"] = df["ALERTA_SIN_USUARIO_SIS"].apply(to_bool)
    df["_TIENE_MATCH_ACADEMICO"] = df["PROGRAM_ID"].notna() if "PROGRAM_ID" in df.columns else False
    if "CREATED_AT_DATE" in df.columns:
        df["_CREATED_AT"] = pd.to_datetime(df["CREATED_AT_DATE"], errors="coerce")
    # FECHA_INICIO_GRUPO es una columna del bloque académico (ver
    # ACADEMICO_COLUMNAS en utils/liff_crm_data.py) que ya viene en esta
    # misma fila unificada -- NULL para prematriculados/sin match, con
    # fecha real para quien sí tiene academia. Se parsea acá (no solo en
    # enrich()) para poder armar _FECHA_CORTE_REF, el criterio híbrido de
    # la regla 5 (ver filtrar_corte_tecnicos_funnel más abajo).
    if "FECHA_INICIO_GRUPO" in df.columns:
        df["_FECHA_INICIO_GRUPO"] = pd.to_datetime(df["FECHA_INICIO_GRUPO"], format="%d/%m/%Y", errors="coerce")
    if "_FECHA_INICIO_GRUPO" in df.columns or "_CREATED_AT" in df.columns:
        inicio = df["_FECHA_INICIO_GRUPO"] if "_FECHA_INICIO_GRUPO" in df.columns else pd.Series(pd.NaT, index=df.index)
        creacion = df["_CREATED_AT"] if "_CREATED_AT" in df.columns else pd.Series(pd.NaT, index=df.index)
        df["_FECHA_CORTE_REF"] = inicio.fillna(creacion)
    return df


def academico_de(df_crm: pd.DataFrame) -> pd.DataFrame:
    """Subconjunto con match académico real (excluye prematriculados y
    matriculados sin usuario SIS), renombrado para reutilizar enrich() y
    todas las funciones académicas de arriba sin duplicarlas.
    PROGRAMA_SIS -> PROGRAMA, ESTADO_ACADEMICO -> ESTADO, DOCUMENTO_SIS ->
    ignorado (ya está CONTACT_DATA_DOCUMENT_ID en el bloque CRM).
    INCREMENTAL_USER_CODE -> ID_SIS: en la query vieja (solo-SIS) esta
    columna SE LLAMABA ID_SIS (alias de E100010.INCREMENTAL_USER_CODE).
    En la unificada es el mismo valor exacto pero expuesto del lado CRM
    como INCREMENTAL_USER_CODE (es la clave con la que se hizo el JOIN
    contra Academico_Detalle) -- se re-alias acá para que _por_estudiante()
    y todo lo que agrupa/ordena por ID_SIS siga funcionando sin tocarlo."""
    aca = df_crm[df_crm["_TIENE_MATCH_ACADEMICO"]].copy()
    return aca.rename(columns={
        "PROGRAMA_SIS": "PROGRAMA",
        "ESTADO_ACADEMICO": "ESTADO",
        "INCREMENTAL_USER_CODE": "ID_SIS",
    })


def _por_persona(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por persona (INCREMENTAL_LEAD_CODE) -- para no contar 2
    veces a quien tiene varias materias en el funnel/KPIs de matrícula."""
    if df.empty or "INCREMENTAL_LEAD_CODE" not in df.columns:
        return df
    return df.drop_duplicates("INCREMENTAL_LEAD_CODE").copy()


def funnel_kpis(df_crm: pd.DataFrame) -> dict:
    """KPIs de cabecera del funnel + calidad de datos, sobre personas
    (no filas/materias)."""
    personas = _por_persona(df_crm)
    total = len(personas)
    matriculados = int((personas["TIPO_MATRICULA"] == "MATRICULADO").sum())
    prematriculados = int((personas["TIPO_MATRICULA"] == "PREMATRICULADO").sum())
    pct_conversion = (matriculados / total * 100) if total else 0.0
    monto_recaudado = personas.loc[personas["TIPO_MATRICULA"] == "MATRICULADO", "ENROLLMENT_DATA_AMOUNT_PAYED"].sum()
    alerta_n = int(personas["_ALERTA_SIN_SIS"].sum())
    alerta_pct = (alerta_n / matriculados * 100) if matriculados else 0.0
    return {
        "total": total,
        "matriculados": matriculados,
        "prematriculados": prematriculados,
        "pct_conversion": pct_conversion,
        "monto_recaudado": float(monto_recaudado) if pd.notna(monto_recaudado) else 0.0,
        "alerta_n": alerta_n,
        "alerta_pct": alerta_pct,
    }


def funnel_por_categoria(df_crm: pd.DataFrame, columna: str, top: int = 15) -> pd.DataFrame:
    """Prematriculados vs Matriculados por asesor / campaña / programa /
    adnetwork -- a nivel persona. `top` limita a las categorías con más
    volumen total (evita gráficas ilegibles si hay muchos asesores)."""
    personas = _por_persona(df_crm)
    if personas.empty or columna not in personas.columns:
        return pd.DataFrame({columna: [], "TIPO_MATRICULA": [], "cantidad": []})
    personas = personas.copy()
    personas[columna] = personas[columna].fillna("(sin dato)")
    top_valores = personas[columna].value_counts().head(top).index
    f = personas[personas[columna].isin(top_valores)]
    out = f.groupby([columna, "TIPO_MATRICULA"], observed=True).size().reset_index(name="cantidad")
    return out


def tendencia_mensual_funnel(df_crm: pd.DataFrame) -> pd.DataFrame:
    """Matriculados/Prematriculados por mes de creación del lead
    (_CREATED_AT, de enrich_crm()), a nivel persona (dedup) -- para ver
    la evolución del funnel, no solo el acumulado."""
    personas = _por_persona(df_crm)
    if personas.empty or "_CREATED_AT" not in personas.columns:
        return pd.DataFrame(columns=["_MES", "TIPO_MATRICULA", "cantidad"])
    d = personas.dropna(subset=["_CREATED_AT"]).copy()
    if d.empty:
        return pd.DataFrame(columns=["_MES", "TIPO_MATRICULA", "cantidad"])
    d["_MES"] = d["_CREATED_AT"].dt.to_period("M").dt.to_timestamp()
    return d.groupby(["_MES", "TIPO_MATRICULA"], observed=True).size().reset_index(name="cantidad")


def alerta_sin_usuario_tabla(df_crm: pd.DataFrame) -> pd.DataFrame:
    """Matriculados sin usuario SIS asociado -- lista accionable (posible
    cédula mal digitada, o falta crear el usuario en el SIS)."""
    personas = _por_persona(df_crm)
    alerta = personas[personas["_ALERTA_SIN_SIS"]]
    cols = [
        c for c in [
            "CONTACT_DATA_FULL_NAME", "CONTACT_DATA_DOCUMENT_ID", "SALES_ADVISOR_FULL_NAME",
            "PROGRAMA_CRM", "CREATED_AT_DATE", "CONTACT_DATA_MOBILE_PHONE",
        ] if c in alerta.columns
    ]
    if "_CREATED_AT" in alerta.columns:
        alerta = alerta.sort_values("_CREATED_AT", ascending=False)
    return alerta[cols]


def academico_resumen_por_persona(df_academico_enriched: pd.DataFrame) -> pd.DataFrame:
    """1 fila por persona con su resumen académico (% aprobación propio,
    nota promedio, retenido) -- insumo para cruzar contra caracterización/
    satisfacción sin arrastrar el grano de materia. Requiere que ya se
    haya llamado enrich() de este mismo módulo sobre el resultado de
    academico_de()."""
    if df_academico_enriched.empty:
        return pd.DataFrame()

    def _resumen(g: pd.DataFrame) -> pd.Series:
        publicadas = g[g["_PUBLICADA"]]
        aprobadas = int((publicadas["_APROBACION"] == "Aprobado").sum())
        total_calificadas = len(publicadas)
        return pd.Series({
            "pct_aprobacion_propio": (aprobadas / total_calificadas * 100) if total_calificadas else pd.NA,
            "nota_promedio_propio": publicadas["_NOTA_NUM"].mean() if len(publicadas) else pd.NA,
            "retenido": g["_RETENIDO"].iloc[0] if "_RETENIDO" in g.columns else pd.NA,
            "materias": len(g),
        })

    return df_academico_enriched.groupby("CONTACT_DATA_DOCUMENT_ID").apply(_resumen).reset_index()
