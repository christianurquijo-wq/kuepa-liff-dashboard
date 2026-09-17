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
    try:
        if value in (None, ""):
            return default
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
    población (sin los filtros de programa/estado del overview)."""

    def _bloque(df: pd.DataFrame) -> dict:
        estudiantes = _por_estudiante(df)
        publicados = df[df["_PUBLICADA"]]
        aprobados = int((publicados["_APROBACION"] == "Aprobado").sum())
        no_aprobados = int((publicados["_APROBACION"] == "No Aprobado").sum())
        total_calificados = aprobados + no_aprobados
        pct_aprobacion = (aprobados / total_calificados * 100) if total_calificados else 0.0
        nota_promedio = publicados["_NOTA_NUM"].mean() if len(publicados) else 0.0
        return {
            "estudiantes": len(estudiantes),
            "modulos": len(df),
            "pct_aprobacion": pct_aprobacion,
            "nota_promedio": nota_promedio if pd.notna(nota_promedio) else 0.0,
        }

    return {"extranjero": _bloque(df_ext), "nacional": _bloque(df_nac)}


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
