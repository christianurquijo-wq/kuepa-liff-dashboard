"""
LIFF -- Empleabilidad.

Fuente: pestaña "Base postulaciones" de la hoja "QUERY Postulaciones Kuepa
Colombia_V.1.0_03062026" (utils/sheets.py::get_base_postulaciones() --
MISMO spreadsheet que ya usa Ecolombia -- Pool de Empleabilidad, mismo
Service Account, sin pasos de configuración nuevos).

oct-2026: auditoría completa de "Base postulaciones" (4.519 filas x 80
columnas) hecha para diseñar este módulo. Hallazgos que definen las reglas
de abajo:

1) La columna "Cohorte" NO separa LIFF de Ecolombia por su VALOR literal --
   trae 3 tipos de valor mezclados: "ECOLOMBIA" (364 filas), "Jovenes a la
   E..." (392 filas, esquema viejo) y nombres de mes tipo "enero 2026"
   (esquema vigente). El FORMATO sí separa limpio: cualquier Cohorte con
   forma "<mes> <año>" es 100% esquema vigente = LIFF -- verificado sobre
   TODA la hoja: 0 filas con Cohorte en ese formato tienen Area="EFE", y
   0 filas sin ese formato tienen Area="HST" (no hay cruce en ningún
   sentido).

   oct-2026 (2): se probó primero filtrar por la columna "Area" (HST vs
   EFE) en vez del formato de Cohorte -- se revirtió por un hallazgo de
   Christian: "Area" tiene un rezago de captura fuerte en el cohorte más
   reciente. De 204 filas con Cohorte="septiembre 2026", 187 (92%) tienen
   Area EN BLANCO, no "HST" -- ese campo aparentemente se llena en un
   paso posterior del proceso, no al matricularse. Filtrar por Area="HST"
   excluía casi todo el cohorte más nuevo (dejaba ver solo 14 de los 20
   extranjeros esperados en agosto+). _cohorte_lift_desde_agosto_2026() (que
   ya parseaba Cohorte para el corte de fecha, ver punto 7) hace las 2
   cosas a la vez -- identifica LIFF Y aplica el corte -- sin depender de
   "Area", que ya no se usa para filtrar en este módulo.

2) "Tipo de documento" tiene casing inconsistente (cc/CC/ppt/PPT/it/ce) --
   se normaliza a mayúsculas antes de clasificar. "IT" (23 filas) se trata
   como sinónimo de "TI" (Tarjeta de Identidad, 1 fila) -- son casi
   con certeza el mismo dato con las letras invertidas por typo, no un
   tipo de documento real distinto. Si esto resulta ser otra cosa, avisa
   para corregir.

3) "Estado Patrocinio" trae un valor basura "HST 2025" (5 filas, parece
   una celda de otra columna pegada en la incorrecta) -- se agrupa junto
   con los NaN en "Sin clasificar", no se inventa a qué etapa
   correspondería.

4) "tiempo en carta" y "tiempo de patrocinio dias" tienen una fracción
   grande de valores corruptos (29% y 10% respectivamente) con magnitud
   de número de serie de fecha de Excel/Sheets (46294, 664788, hasta
   -1.005.851.844 en "Tiempo de contratación pago/contrato") -- huele a
   una fórmula de resta de fechas que devuelve la fecha cruda cuando una
   de las 2 celdas está vacía, en vez de un error o blanco. Se descartan
   valores con |valor| > CORTE_DIAS_INVALIDO (3.650 días = 10 años,
   generoso a propósito) en vez de intentar adivinar la fórmula rota --
   sobre el subconjunto limpio los valores reales van de 0 a ~280-450
   días, así que el corte no descarta datos legítimos.

5) "Base postulaciones" NO tiene una columna "Tiempo en el Pool" (esa
   vive en la pestaña "TiempoEnPool", que ya usa Ecolombia) -- se usa
   "tiempo de patrocinio dias" como métrica de tiempo equivalente, con
   nombre propio ("Tiempo de patrocinio") para no confundirla con el
   "Tiempo en el Pool" de Ecolombia, que es un cálculo distinto.

6) "Empresa Patrocinadora" y "Asesor" tienen espacios sueltos al final en
   algunas filas (ej. "OXXO" y "OXXO " cuentan separado sin strip()) --
   se normalizan con .str.strip().

7) sept-2026 (Christian): la página debe mostrar la MISMA línea de tiempo
   que el resto del dashboard LIFF Data -- "grupo iniciado >= 2026-08-01"
   (ver queries/liff_data.py). En "Base postulaciones" hay 2 columnas que
   podrían servir para esto y NO son intercambiables:
     - "Cohorte" (mes+año, ej. "agosto 2026") -- mismo concepto que
       "grupo iniciado" del resto del dash. Confirmado con Christian: se
       usa esta.
     - "Mes de ingreso al proceso de empleabilidad" (columna CA) -- solo
       el nombre del mes, SIN año (ej. "septiembre") -- no se puede
       filtrar por año de forma confiable con este dato, se descartó.
   CORTE_COHORTE_DESDE define el corte (2026, 8) -- filas con Cohorte
   anterior a agosto 2026 (o que no matchean el formato "<mes> <año>", ver
   punto 1) se excluyen en enrich(). Muestra resultante: 581 filas -- es
   lo esperado, no un bug: el resto del dashboard tiene el mismo recorte
   de fecha.

NO hay un pantallazo de Looker ni ninguna otra fuente para validar estos
números número-por-número (a diferencia de
utils/ecolombia_empleabilidad_metrics.py, que sí lo tiene) -- son
categorías construidas directo del diccionario de datos y el value_counts
real. Si algún número no cuadra con lo que ve Christian en el proceso
real, referenciar este docstring para saber qué regla ajustar.
"""
import pandas as pd

CORTE_DIAS_INVALIDO = 3650  # ver punto (4) -- valores con |x| > esto son basura de fórmula, no días reales

# ver punto (7) -- mismo criterio que "grupo iniciado >= 2026-08-01" del resto de LIFF Data
_MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
CORTE_COHORTE_DESDE = (2026, 8)  # agosto 2026

DOC_EXTRANJERO = {"PPT", "CE", "PS", "DE"}
DOC_NACIONAL = {"CC", "TI", "IT"}  # "IT" tratado como "TI" -- ver punto (2)

ESTADOS_CONTRATADO = ["Aprobado/Patrocinado", "Otro tipo de contrato"]
ESTADOS_SALIDA = ["Baja", "Matricula no Exitosa", "Prospecto Caido", "No patrocinable"]
ESTADOS_SIN_CLASIFICAR = ["HST 2025"]  # ver punto (3) -- se suma a los NaN

# Orden del funnel -- de "no ha empezado" a "contratado". Los ESTADOS_SALIDA
# (baja, no exitosa, etc.) NO entran acá: pueden pasar desde cualquier etapa,
# forzarlos a una posición del funnel sería inventar un orden que no existe.
ORDEN_FUNNEL = ["sin proceso", "En Proceso", "Carta de presentación", "Proceso Avanzado", "Contratado/Patrocinado"]

_COLS_TEXTO_STRIP = ["Empresa Patrocinadora", "Asesor", "Programa ", "Estado Patrocinio", "Tipo de documento"]


def _a_numero(serie: pd.Series) -> pd.Series:
    """Coma decimal es-CO -> float, celdas vacías -> NaN. Mismo criterio
    que utils/liff_metrics.py::to_float() y
    utils/ecolombia_empleabilidad_metrics.py::_a_numero()."""
    return pd.to_numeric(
        serie.astype(str).str.strip().str.replace(",", ".", regex=False).replace({"": None, "nan": None}),
        errors="coerce",
    )


def _tiempo_valido(serie: pd.Series) -> pd.Series:
    """_a_numero() + descarta basura de fórmula -- ver punto (4)."""
    num = _a_numero(serie)
    return num.where(num.abs() <= CORTE_DIAS_INVALIDO)


def _poblacion(tipo_doc: pd.Series) -> pd.Series:
    doc = tipo_doc.astype(str).str.strip().str.upper()
    resultado = pd.Series(pd.NA, index=tipo_doc.index, dtype="object")
    resultado[doc.isin(DOC_NACIONAL)] = "Nacionales"
    resultado[doc.isin(DOC_EXTRANJERO)] = "Extranjeros"
    return resultado


def _cohorte_lift_desde_agosto_2026(serie: pd.Series) -> pd.Series:
    """True si "Cohorte" tiene formato "<mes> <año>" (= esquema vigente =
    LIFF, ver punto 1) Y ese mes/año es >= CORTE_COHORTE_DESDE (ver punto
    7). Hace las 2 cosas en un solo paso porque son el mismo parseo:
    Cohorte no reconocible (formato viejo tipo "ECOLOMBIA", mes no-es, o
    vacío) se descarta (False) en vez de asumir que sí cumple."""
    partes = serie.astype(str).str.strip().str.lower().str.split(" ", n=1, expand=True)
    if partes.shape[1] < 2:
        return pd.Series(False, index=serie.index)
    mes = partes[0].map(_MESES_ES)
    anio = pd.to_numeric(partes[1], errors="coerce")
    anio_mes = anio * 12 + mes
    corte = CORTE_COHORTE_DESDE[0] * 12 + CORTE_COHORTE_DESDE[1]
    return anio_mes.fillna(-1) >= corte


def enrich(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Filtra a filas LIFF con Cohorte >= agosto 2026 en un solo paso
    (ver puntos 1 y 7 -- NO se filtra por "Area", tiene rezago de captura
    fuerte en el cohorte más reciente), y agrega las columnas derivadas
    que usan las funciones de abajo. Devuelve DataFrame vacío si faltan
    columnas clave (la página debe avisar, no reventar)."""
    requeridas = {"Cohorte", "Tipo de documento", "Estado Patrocinio"}
    if df_raw.empty or not requeridas.issubset(df_raw.columns):
        return pd.DataFrame()

    df = df_raw[_cohorte_lift_desde_agosto_2026(df_raw["Cohorte"])].copy()
    if df.empty:
        return df

    for col in _COLS_TEXTO_STRIP:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA})

    df["_POBLACION"] = _poblacion(df["Tipo de documento"])

    estado = df["Estado Patrocinio"]
    df["_ESTADO"] = estado.where(~estado.isin(ESTADOS_SIN_CLASIFICAR), pd.NA).fillna("Sin clasificar")
    # Etapa de funnel: colapsa los 2 estados "contratado" en una sola
    # categoría (ver ORDEN_FUNNEL) -- las salidas y "Sin clasificar" quedan
    # fuera del funnel propiamente (se muestran aparte).
    df["_ETAPA_FUNNEL"] = df["_ESTADO"].where(
        ~df["_ESTADO"].isin(ESTADOS_CONTRATADO), "Contratado/Patrocinado"
    )

    if "cantidad de proceso" in df.columns:
        df["_CANTIDAD_PROCESO"] = _a_numero(df["cantidad de proceso"])
    if "tiempo en carta" in df.columns:
        df["_TIEMPO_CARTA"] = _tiempo_valido(df["tiempo en carta"])
    if "tiempo de patrocinio dias" in df.columns:
        df["_TIEMPO_PATROCINIO"] = _tiempo_valido(df["tiempo de patrocinio dias"])

    return df.reset_index(drop=True)


def kpis_poblacion(df: pd.DataFrame) -> dict:
    """KPIs de cabecera "X vs Y" -- cantidades absolutas, Extranjeros vs
    Nacionales (mismo estilo que el resto del dashboard)."""
    vacio = {"Extranjeros": 0, "Nacionales": 0}
    if df.empty:
        return {"total": dict(vacio), "contratados": dict(vacio), "en_pool": dict(vacio), "salida": dict(vacio)}

    def _contar(mask):
        return {p: int(((df["_POBLACION"] == p) & mask).sum()) for p in ("Extranjeros", "Nacionales")}

    en_pool_mask = df["_ETAPA_FUNNEL"].isin(["sin proceso", "En Proceso", "Carta de presentación", "Proceso Avanzado"])
    return {
        "total": _contar(pd.Series(True, index=df.index)),
        "contratados": _contar(df["_ETAPA_FUNNEL"] == "Contratado/Patrocinado"),
        "en_pool": _contar(en_pool_mask),
        "salida": _contar(df["_ESTADO"].isin(ESTADOS_SALIDA)),
    }


def funnel_poblacion(df: pd.DataFrame) -> pd.DataFrame:
    """Etapas del funnel como % del total de CADA población (no del
    combinado) -- mismo criterio que el resto de comparaciones
    Extranjeros/Nacionales del dashboard, para que el grupo chico
    (Extranjeros) no quede invisible al lado del grande."""
    columnas = ["etapa", "poblacion", "porcentaje", "cantidad"]
    if df.empty:
        return pd.DataFrame(columns=columnas)

    filas = []
    for poblacion in ("Extranjeros", "Nacionales"):
        sub = df[df["_POBLACION"] == poblacion]
        total = len(sub)
        counts = sub["_ETAPA_FUNNEL"].value_counts()
        for etapa in ORDEN_FUNNEL:
            cantidad = int(counts.get(etapa, 0))
            pct = (cantidad / total * 100) if total else 0.0
            filas.append({"etapa": etapa, "poblacion": poblacion, "porcentaje": pct, "cantidad": cantidad})
    return pd.DataFrame(filas, columns=columnas)


def salidas_poblacion(df: pd.DataFrame) -> pd.DataFrame:
    """Estados de salida (Baja/Matricula no Exitosa/Prospecto Caido/No
    patrocinable) -- separados del funnel porque pueden pasar desde
    cualquier etapa, no son "el paso siguiente". % de cada población."""
    columnas = ["estado", "poblacion", "porcentaje", "cantidad"]
    if df.empty:
        return pd.DataFrame(columns=columnas)

    filas = []
    for poblacion in ("Extranjeros", "Nacionales"):
        sub = df[df["_POBLACION"] == poblacion]
        total = len(sub)
        counts = sub["_ESTADO"].value_counts()
        for estado in ESTADOS_SALIDA:
            cantidad = int(counts.get(estado, 0))
            pct = (cantidad / total * 100) if total else 0.0
            filas.append({"estado": estado, "poblacion": poblacion, "porcentaje": pct, "cantidad": cantidad})
    return pd.DataFrame(filas, columns=columnas)


def tiempos_poblacion(df: pd.DataFrame) -> pd.DataFrame:
    """Promedio y mediana de tiempo en carta / tiempo de patrocinio,
    Extranjeros vs Nacionales -- ver punto (4)/(5) del docstring del
    módulo (valores de fórmula rota ya descartados en enrich())."""
    columnas = ["metrica", "poblacion", "promedio", "mediana", "n"]
    metricas = {"Tiempo en carta (días)": "_TIEMPO_CARTA", "Tiempo de patrocinio (días)": "_TIEMPO_PATROCINIO"}
    if df.empty or not any(c in df.columns for c in metricas.values()):
        return pd.DataFrame(columns=columnas)

    filas = []
    for etiqueta, col in metricas.items():
        if col not in df.columns:
            continue
        for poblacion in ("Extranjeros", "Nacionales"):
            valores = df.loc[df["_POBLACION"] == poblacion, col].dropna()
            filas.append({
                "metrica": etiqueta, "poblacion": poblacion,
                "promedio": float(valores.mean()) if len(valores) else 0.0,
                "mediana": float(valores.median()) if len(valores) else 0.0,
                "n": int(len(valores)),
            })
    return pd.DataFrame(filas, columns=columnas)


def empresas_top(df: pd.DataFrame, top: int = 15) -> pd.DataFrame:
    """Ranking de empresas por cantidad de estudiantes asociados
    (Empresa Patrocinadora no vacía), con % de esos que quedaron
    Aprobado/Patrocinado -- proxy de tasa de aprobación por empresa (es
    el estado ACTUAL del estudiante, no un resultado por-postulación
    puntual, ver limitación en el docstring del módulo)."""
    columnas = ["empresa", "estudiantes", "aprobados", "pct_aprobacion"]
    if df.empty or "Empresa Patrocinadora" not in df.columns:
        return pd.DataFrame(columns=columnas)

    con_empresa = df.dropna(subset=["Empresa Patrocinadora"])
    if con_empresa.empty:
        return pd.DataFrame(columns=columnas)

    agrupado = con_empresa.groupby("Empresa Patrocinadora").agg(
        estudiantes=("_ESTADO", "size"),
        aprobados=("_ETAPA_FUNNEL", lambda s: int((s == "Contratado/Patrocinado").sum())),
    ).reset_index().rename(columns={"Empresa Patrocinadora": "empresa"})
    agrupado["pct_aprobacion"] = (agrupado["aprobados"] / agrupado["estudiantes"] * 100).round(1)
    return agrupado.sort_values("estudiantes", ascending=False).head(top).reset_index(drop=True)


def resumen_por_dimension_poblacion(df: pd.DataFrame, columna: str, top: int = 12) -> pd.DataFrame:
    """% de estudiantes por `columna` (Programa/Asesor) sobre el total de
    CADA población, + % de contratación dentro de esa categoría -- mismo
    patrón que academico_resumen_por_dimension_poblacion() en
    utils/liff_metrics.py."""
    columnas = [columna, "poblacion", "pct_estudiantes", "estudiantes", "pct_contratacion"]
    if df.empty or columna not in df.columns:
        return pd.DataFrame(columns=columnas)

    total_por_poblacion = {p: int((df["_POBLACION"] == p).sum()) for p in ("Extranjeros", "Nacionales")}

    filas = []
    for poblacion in ("Extranjeros", "Nacionales"):
        sub = df[df["_POBLACION"] == poblacion]
        total_pob = total_por_poblacion[poblacion]
        if sub.empty:
            continue
        d = sub.copy()
        d[columna] = d[columna].fillna("(sin dato)")
        for valor, g in d.groupby(columna, observed=True):
            estudiantes = len(g)
            contratados = int((g["_ETAPA_FUNNEL"] == "Contratado/Patrocinado").sum())
            filas.append({
                columna: valor, "poblacion": poblacion,
                "pct_estudiantes": (estudiantes / total_pob * 100) if total_pob else 0.0,
                "estudiantes": estudiantes,
                "pct_contratacion": (contratados / estudiantes * 100) if estudiantes else 0.0,
            })
    out = pd.DataFrame(filas, columns=columnas)
    if out.empty:
        return out
    top_valores = out.groupby(columna)["estudiantes"].sum().sort_values(ascending=False).head(top).index
    return out[out[columna].isin(top_valores)]
