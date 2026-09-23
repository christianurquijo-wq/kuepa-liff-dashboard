"""
Reglas de negocio -- IQ (alianza IQP / IQS / IQ512).

Separado de utils/iq_data.py a propósito: ese módulo SOLO lee y tipa: este
calcula. Todas las reglas obligatorias del prompt de Christian están
numeradas abajo con el mismo número que en 00_PROMPT_MAESTRO.md /
03_diccionario_datos.md, para poder rastrear cada una hasta su origen.

(1) Se cuenta por USER_ID (usuarios) / user_log_view (lecciones), nunca
    por ID_SIS -- ID_SIS solo se usa para MOSTRAR en tablas (es_id_sis_compartido()
    existe justo para demostrar por qué contar por ID_SIS subestima).
(2) Privacidad: no hay nombre/correo en los datos que llegan aquí -- no se
    reconstruyen en ningún punto de este archivo.
(3) fecha_de_corte() -- moda de EFFECTIVE_LAST_ACCESS.normalize() + DAYS_SINCE_ACCESS.
(4) DAYS_SINCE_ACCESS vacío -> segmento "Sin acceso" propio, nunca se trata como 0
    (ver segmento_recencia(): el NaN se reemplaza por la etiqueta, no por un número).
(5) fuente_fecha() -- Acceso / Login / Solo log / Sin fecha.
(6) carga_masiva_iq512 -- flag + excluir_carga_masiva en kpis_recencia_por_programa().
(7) TIME_VIEW en segundos -> minutos/horas al mostrar; nunca se suma con Horas_uso.
(8) cobertura_lecciones() -- "N usuarios con lecciones de M totales", obligatorio
    en cualquier gráfico de lecciones.
(9) Fecha de lecciones = fecha de la vista con más horas, se usa solo por año/mes,
    nunca como serie de tiempo continua.
(10) Nivel de IQ512 = curso/edición, no grado -- por eso NUNCA se agrupan juntos
     (ver desglose_por_nivel(), que separa por Tipo_nivel). excluir_cuentas_internas
     filtra Es_interno.
(11) SEGMENTOS_RECENCIA / BANDAS_TIEMPO -- categorías fijas, ver abajo.
"""
from datetime import date

import numpy as np
import pandas as pd

FECHA_CARGA_MASIVA_IQ512 = date(2022, 10, 1)

SEGMENTOS_RECENCIA = ["≤30 d", "31–90", "91–180", "181–365", ">365", "Sin acceso"]
_BINS_RECENCIA = [-0.1, 30, 90, 180, 365, np.inf]
_LABELS_RECENCIA = ["≤30 d", "31–90", "91–180", "181–365", ">365"]

BANDAS_TIEMPO = ["0", "<10 min", "10–30 min", "30–60 min", "1–2 h", "2–5 h", "5–10 h", ">10 h"]
_BINS_TIEMPO_SEG = [-0.1, 0, 600, 1800, 3600, 7200, 18000, 36000, np.inf]

PROGRAMAS = ["IQP", "IQS", "IQ512"]


# ---------------------------------------------------------------------------
# Enriquecimiento (agrega columnas derivadas, no filtra nada todavía)
# ---------------------------------------------------------------------------
def segmento_recencia(dias: pd.Series) -> pd.Categorical:
    """Regla (11)/(4): NaN -> "Sin acceso" como categoría propia, no como 0
    ni como bin descartado por pd.cut."""
    seg = pd.cut(dias, bins=_BINS_RECENCIA, labels=_LABELS_RECENCIA).astype(object)
    seg[dias.isna()] = "Sin acceso"
    return pd.Categorical(seg, categories=SEGMENTOS_RECENCIA, ordered=True)


def banda_tiempo(segundos: pd.Series) -> pd.Categorical:
    """Regla (11)/(7): TIME_VIEW en segundos -> banda legible."""
    banda = pd.cut(segundos, bins=_BINS_TIEMPO_SEG, labels=BANDAS_TIEMPO)
    return pd.Categorical(banda, categories=BANDAS_TIEMPO, ordered=True)


def enrich_usuarios(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega fuente_fecha, carga_masiva_iq512, segmento_recencia,
    banda_tiempo. NO filtra nada -- los interruptores de la barra lateral
    filtran sobre el resultado de esta función, en la página."""
    if df.empty:
        return df
    df = df.copy()

    # Regla (5) -- mismo orden de prioridad que el COALESCE de
    # EFFECTIVE_LAST_ACCESS en el SQL (Acceso > Login > Solo log).
    df["fuente_fecha"] = np.select(
        [
            df["MAX_LAST_ACCESS"].notna(),
            df["MAX_LAST_LOGIN"].notna(),
            df["MAX_LOG_DATE"].notna(),
        ],
        ["Acceso", "Login", "Solo log"],
        default="Sin fecha",
    )

    # Regla (6) -- 18.224 usuarios de IQ512, MAX_LOG_DATE=2022-10-01 y sin
    # acceso/login registrado -- no es actividad real, es una carga masiva.
    df["carga_masiva_iq512"] = (
        (df["PROGRAMA"] == "IQ512")
        & (df["MAX_LOG_DATE"].dt.date == FECHA_CARGA_MASIVA_IQ512)
        & df["MAX_LAST_ACCESS"].isna()
        & df["MAX_LAST_LOGIN"].isna()
    )

    df["segmento_recencia"] = segmento_recencia(df["DAYS_SINCE_ACCESS"])
    df["banda_tiempo"] = banda_tiempo(df["TIME_VIEW"])
    return df


def enrich_lecciones(df: pd.DataFrame) -> pd.DataFrame:
    """Sin transformación pesada -- Es_interno y los tipos ya vienen
    listos de iq_data.load_iq_lecciones(). Existe por simetría con
    enrich_usuarios() y como punto único si aparece una regla nueva."""
    return df.copy() if not df.empty else df


# ---------------------------------------------------------------------------
# Fecha de corte (regla 3)
# ---------------------------------------------------------------------------
def fecha_de_corte(df_usuarios: pd.DataFrame) -> date | None:
    """Moda de (EFFECTIVE_LAST_ACCESS normalizada + DAYS_SINCE_ACCESS días)
    -- reconstruye la fecha en que se corrió la consulta SQL, SIN usar
    date.today() (que envejecería con cada visita a la página)."""
    validos = df_usuarios.dropna(subset=["EFFECTIVE_LAST_ACCESS", "DAYS_SINCE_ACCESS"])
    if validos.empty:
        return None
    candidatas = validos["EFFECTIVE_LAST_ACCESS"].dt.normalize() + pd.to_timedelta(
        validos["DAYS_SINCE_ACCESS"], unit="D"
    )
    moda = candidatas.mode()
    if moda.empty:
        return None
    return moda.iloc[0].date()


# ---------------------------------------------------------------------------
# Sección 1 -- Resumen y recencia
# ---------------------------------------------------------------------------
def kpis_recencia_por_programa(df: pd.DataFrame, excluir_carga_masiva: bool = True) -> pd.DataFrame:
    """"Usuarios" siempre es el total real del programa (no cambia con el
    interruptor). El interruptor (regla 6) solo saca la carga masiva de
    IQ512 de la BASE que alimenta %≤30d/%≤90d/%nunca ingresó/mediana --
    si se dejan adentro, esos 18.224 registros (56 % de IQ512, todos con
    el mismo DAYS_SINCE_ACCESS=1448) distorsionan la mediana y el % que
    "nunca ingresó" hacia un patrón que no es actividad real."""
    filas = []
    for programa in PROGRAMAS:
        total_sub = df[df["PROGRAMA"] == programa]
        total = len(total_sub)
        if total == 0:
            continue
        base = total_sub[~total_sub["carga_masiva_iq512"]] if excluir_carga_masiva else total_sub
        base_n = len(base)
        dias = base["DAYS_SINCE_ACCESS"]
        sin_acceso = int(dias.isna().sum())
        filas.append(
            {
                "Programa": programa,
                "Usuarios": total,
                "Base recencia": base_n,
                "% ≤30 d": (dias.le(30).sum() / base_n * 100) if base_n else 0.0,
                "% ≤90 d": (dias.le(90).sum() / base_n * 100) if base_n else 0.0,
                "% nunca ingresó": (sin_acceso / base_n * 100) if base_n else 0.0,
                "Mediana días sin acceso": dias.median(),
            }
        )
    return pd.DataFrame(filas)


def segmentos_por_programa(df: pd.DataFrame, excluir_carga_masiva: bool = True) -> pd.DataFrame:
    """Conteo por (Programa, segmento_recencia) -- insumo de la barra
    100% apilada. Fuerza los 6 segmentos con 0 si faltan, para que la
    barra no pierda un color."""
    base = df[~df["carga_masiva_iq512"]] if excluir_carga_masiva else df
    filas = []
    for programa in PROGRAMAS:
        sub = base[base["PROGRAMA"] == programa]
        total = len(sub)
        for seg in SEGMENTOS_RECENCIA:
            cantidad = int((sub["segmento_recencia"] == seg).sum())
            filas.append(
                {
                    "Programa": programa,
                    "Segmento": seg,
                    "Usuarios": cantidad,
                    "Porcentaje": (cantidad / total * 100) if total else 0.0,
                }
            )
    return pd.DataFrame(filas)


def tendencia_mensual_acceso(df: pd.DataFrame, excluir_carga_masiva: bool = True) -> pd.DataFrame:
    """Usuarios por (año-mes de EFFECTIVE_LAST_ACCESS, Programa) -- para
    la línea/barra de tendencia. Se excluyen los "Sin acceso" (no tienen
    mes) y, por defecto, la carga masiva de IQ512 (regla 6) porque cae
    toda en un solo mes (2022-10) y aplastaría la escala del resto."""
    base = df[~df["carga_masiva_iq512"]] if excluir_carga_masiva else df
    base = base.dropna(subset=["EFFECTIVE_LAST_ACCESS"])
    if base.empty:
        return pd.DataFrame(columns=["mes", "Programa", "Usuarios"])
    tmp = base.copy()
    # tz_convert(None) antes de to_period() -- to_period no soporta tz y
    # tira un UserWarning en cada corrida si no se quita primero (los
    # timestamps ya vienen en UTC, no se pierde información real).
    tmp["mes"] = tmp["EFFECTIVE_LAST_ACCESS"].dt.tz_convert(None).dt.to_period("M").dt.to_timestamp()
    out = tmp.groupby(["mes", "PROGRAMA"], observed=True).size().reset_index(name="Usuarios")
    return out.rename(columns={"PROGRAMA": "Programa"})


# ---------------------------------------------------------------------------
# Sección 2 -- Uso y tiempo (regla 7: TIME_VIEW en segundos)
# ---------------------------------------------------------------------------
def kpis_tiempo_por_programa(df: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for programa in PROGRAMAS:
        sub = df[df["PROGRAMA"] == programa]
        if sub.empty:
            continue
        filas.append(
            {
                "Programa": programa,
                "Usuarios": len(sub),
                "Tiempo promedio (min)": sub["TIME_VIEW"].mean() / 60,
                "Tiempo mediana (min)": sub["TIME_VIEW"].median() / 60,
                "Registros promedio": sub["REGISTROS"].mean(),
            }
        )
    return pd.DataFrame(filas)


def banda_tiempo_por_programa(df: pd.DataFrame) -> pd.DataFrame:
    out = df.groupby(["PROGRAMA", "banda_tiempo"], observed=False).size().reset_index(name="Usuarios")
    return out.rename(columns={"PROGRAMA": "Programa", "banda_tiempo": "Banda"})


def matriz_recencia_uso(df: pd.DataFrame, excluir_carga_masiva: bool = True) -> pd.DataFrame:
    """Recencia x banda de uso, con conteo -- insumo del mapa de calor."""
    base = df[~df["carga_masiva_iq512"]] if excluir_carga_masiva else df
    out = (
        base.groupby(["segmento_recencia", "banda_tiempo"], observed=False)
        .size()
        .reset_index(name="Usuarios")
    )
    return out


# ---------------------------------------------------------------------------
# Sección 3 -- Lecciones consumidas
# ---------------------------------------------------------------------------
def cobertura_lecciones(df_usuarios: pd.DataFrame, df_lecciones: pd.DataFrame) -> pd.DataFrame:
    """Regla (8), obligatoria en cualquier gráfico de lecciones: "N
    usuarios con lecciones de M totales". Cuenta por user_log_view
    (regla 1), no por filas de lecciones (un usuario puede tener varias)."""
    filas = []
    for programa in PROGRAMAS:
        total_usuarios = int((df_usuarios["PROGRAMA"] == programa).sum())
        sub_lec = df_lecciones[df_lecciones["Programa"] == programa]
        usuarios_con_lecciones = sub_lec["user_log_view"].nunique()
        filas.append(
            {
                "Programa": programa,
                "Usuarios con lecciones": usuarios_con_lecciones,
                "Usuarios totales": total_usuarios,
                "Cobertura %": (usuarios_con_lecciones / total_usuarios * 100) if total_usuarios else 0.0,
                "Filas": len(sub_lec),
                "Horas (ajustadas)": sub_lec["Horas_uso_ajustada"].sum(),
            }
        )
    return pd.DataFrame(filas)


def horas_por_area(df_lecciones: pd.DataFrame) -> pd.DataFrame:
    out = (
        df_lecciones.groupby(["Programa", "Area_Conocimiento"], observed=True)
        .agg(Horas=("Horas_uso_ajustada", "sum"), Usuarios=("user_log_view", "nunique"), Filas=("Programa", "size"))
        .reset_index()
        .sort_values("Horas", ascending=False)
    )
    return out


def desglose_por_nivel(df_lecciones: pd.DataFrame, programa: str) -> pd.DataFrame:
    """Regla (10): Nivel de IQ512 son cursos/ediciones, NUNCA se mezclan
    con los grados de IQP/IQS -- por eso esta función recibe un único
    `programa` a la vez, la página la llama por separado para cada uno."""
    sub = df_lecciones[df_lecciones["Programa"] == programa]
    if sub.empty:
        return pd.DataFrame(columns=["Nivel", "Filas", "Usuarios", "Horas"])
    out = (
        sub.groupby("Nivel", observed=True)
        .agg(Filas=("Programa", "size"), Usuarios=("user_log_view", "nunique"), Horas=("Horas_uso_ajustada", "sum"))
        .reset_index()
        .sort_values("Filas", ascending=False)
    )
    return out


def top_componentes(df_lecciones: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    out = (
        df_lecciones.groupby(["Programa", "Componente_academico"], observed=True)
        .agg(Filas=("Programa", "size"), Usuarios=("user_log_view", "nunique"), Horas=("Horas_uso_ajustada", "sum"))
        .reset_index()
        .sort_values("Filas", ascending=False)
        .head(n)
    )
    return out


def lecciones_por_anio(df_lecciones: pd.DataFrame) -> pd.DataFrame:
    """Regla (9): Anio es el año de la VISTA con más horas de ese
    (usuario, área, componente), no una serie de tiempo de actividad --
    se rotula así en la página, este agregado es válido tal cual."""
    out = df_lecciones.groupby(["Anio", "Programa"], observed=True).size().reset_index(name="Filas")
    return out.sort_values("Anio")


def lecciones_pero_sin_acceso(df_usuarios: pd.DataFrame, df_lecciones: pd.DataFrame) -> pd.DataFrame:
    """Cruce de la regla 8: usuarios con lecciones pero segmento "Sin
    acceso" en la hoja 1 -- las fechas de acceso no registran todo el
    consumo (ver 03_diccionario_datos.md)."""
    sin_acceso_ids = set(df_usuarios.loc[df_usuarios["segmento_recencia"] == "Sin acceso", "USER_ID"])
    filas = []
    for programa in PROGRAMAS:
        ids_programa = set(df_lecciones.loc[df_lecciones["Programa"] == programa, "user_log_view"])
        interseccion = ids_programa & {
            uid for uid in sin_acceso_ids if uid in set(df_usuarios.loc[df_usuarios["PROGRAMA"] == programa, "USER_ID"])
        }
        filas.append({"Programa": programa, "Usuarios con lecciones pero Sin acceso": len(interseccion)})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Sección 4 -- Usuarios y calidad de datos
# ---------------------------------------------------------------------------
def tabla_usuarios(df_usuarios: pd.DataFrame, df_lecciones: pd.DataFrame) -> pd.DataFrame:
    """Una fila por usuario -- Programa, segmento, días, tiempo,
    registros, lecciones y horas. Base de la tabla filtrable/descargable
    de la sección 4.

    Tolera una hoja de lecciones vacía (programa sin ninguna fila de
    lecciones, o la hoja completa vacía) -- caso de prueba explícito del
    prompt. Sin este chequeo, el groupby de abajo revienta con KeyError
    porque "Horas_uso_ajustada" no existe en un DataFrame vacío sin esa
    columna."""
    requeridas_lecciones = {"Programa", "user_log_view", "Horas_uso_ajustada"}
    if df_lecciones is None or df_lecciones.empty or not requeridas_lecciones.issubset(df_lecciones.columns):
        out = df_usuarios.copy()
        out["Lecciones"] = 0
        out["Horas_lecciones"] = 0.0
    else:
        resumen_lecciones = (
            df_lecciones.groupby(["Programa", "user_log_view"], observed=True)
            .agg(Lecciones=("Programa", "size"), Horas_lecciones=("Horas_uso_ajustada", "sum"))
            .reset_index()
            .rename(columns={"user_log_view": "USER_ID", "Programa": "PROGRAMA"})
        )
        out = df_usuarios.merge(resumen_lecciones, on=["PROGRAMA", "USER_ID"], how="left")
        out["Lecciones"] = out["Lecciones"].fillna(0).astype(int)
        out["Horas_lecciones"] = out["Horas_lecciones"].fillna(0.0)
    out["Tiempo (min)"] = out["TIME_VIEW"] / 60
    columnas = [
        "PROGRAMA", "ID_SIS", "segmento_recencia", "DAYS_SINCE_ACCESS",
        "Tiempo (min)", "REGISTROS", "Lecciones", "Horas_lecciones", "fuente_fecha",
    ]
    return out[columnas].rename(
        columns={
            "PROGRAMA": "Programa", "segmento_recencia": "Segmento", "DAYS_SINCE_ACCESS": "Días sin acceso",
            "REGISTROS": "Registros", "fuente_fecha": "Fuente fecha",
        }
    )


def id_sis_compartidos(df_usuarios: pd.DataFrame) -> dict:
    """Regla (1): por qué NO se cuenta por ID_SIS. 1.057 ID_SIS se
    repiten entre 2.372 USER_ID -- ID_SIS no es llave."""
    con_id = df_usuarios.dropna(subset=["ID_SIS"])
    conteo = con_id.groupby("ID_SIS", observed=True)["USER_ID"].nunique()
    compartidos = conteo[conteo > 1]
    return {
        "id_sis_compartidos": int(len(compartidos)),
        "usuarios_involucrados": int(compartidos.sum()),
        "usuarios_sin_id_sis": int(df_usuarios["ID_SIS"].isna().sum()),
    }


def calidad_lecciones(df_lecciones: pd.DataFrame) -> dict:
    duplicados = df_lecciones.duplicated(
        subset=["Programa", "user_log_view", "Area_Conocimiento", "Componente_academico"]
    ).sum()
    return {
        "filas": len(df_lecciones),
        "sin_horas": int(df_lecciones["Horas_uso_raw"].isna().sum()),
        "sin_status": int(df_lecciones["Status_pct"].isna().sum()) if "Status_pct" in df_lecciones.columns else None,
        "duplicados": int(duplicados),
    }


def calidad_solo_log_y_carga_masiva(df_usuarios: pd.DataFrame) -> dict:
    return {
        "solo_log": int((df_usuarios["fuente_fecha"] == "Solo log").sum()),
        "carga_masiva_iq512": int(df_usuarios["carga_masiva_iq512"].sum()),
    }


# ---------------------------------------------------------------------------
# Autoverificación (regla de "Calidad y verificación" del prompt) -- compara
# contra 04_hallazgos_y_valores_referencia.md, SIEMPRE sobre datos crudos sin
# filtrar (sin el interruptor de carga masiva) porque así se calcularon los
# valores de ese archivo. No corre contra la selección de la barra lateral.
# ---------------------------------------------------------------------------
REFERENCIA_HALLAZGOS = {
    "usuarios_IQP": 79038, "usuarios_IQS": 439006, "usuarios_IQ512": 32489, "usuarios_total": 550533,
    "sin_acceso_IQP": 10835, "sin_acceso_IQS": 129393, "sin_acceso_IQ512": 7247, "sin_acceso_total": 147475,
    "accedieron_30d_IQP": 32, "accedieron_30d_IQS": 979, "accedieron_30d_IQ512": 33,
    "mediana_dias_IQP": 1057, "mediana_dias_IQS": 843, "mediana_dias_IQ512": 1448,
    "id_sis_compartidos": 1057, "id_sis_usuarios_involucrados": 2372,
}


def _self_check(df_usuarios_crudo: pd.DataFrame) -> list[dict]:
    """Devuelve una lista de {label, esperado, real, ok} -- la página
    muestra un st.warning si algún `ok` es False. Tolerancia de +-1 para
    absorber redondeos/actualizaciones menores de la hoja."""
    resultados = []

    def _check(label, esperado, real, tolerancia=1):
        ok = abs((real or 0) - esperado) <= tolerancia
        resultados.append({"label": label, "esperado": esperado, "real": real, "ok": ok})

    if df_usuarios_crudo.empty:
        return resultados

    por_programa = df_usuarios_crudo.groupby("PROGRAMA", observed=True)
    for programa in PROGRAMAS:
        if programa not in por_programa.groups:
            continue
        sub = por_programa.get_group(programa)
        _check(f"Usuarios {programa}", REFERENCIA_HALLAZGOS[f"usuarios_{programa}"], len(sub))
        _check(f"Sin acceso {programa}", REFERENCIA_HALLAZGOS[f"sin_acceso_{programa}"], int(sub["DAYS_SINCE_ACCESS"].isna().sum()))
        _check(f"Accedieron ≤30d {programa}", REFERENCIA_HALLAZGOS[f"accedieron_30d_{programa}"], int(sub["DAYS_SINCE_ACCESS"].le(30).sum()))
        mediana = sub["DAYS_SINCE_ACCESS"].median()
        _check(f"Mediana días {programa}", REFERENCIA_HALLAZGOS[f"mediana_dias_{programa}"], mediana, tolerancia=2)

    _check("Usuarios total", REFERENCIA_HALLAZGOS["usuarios_total"], len(df_usuarios_crudo))
    _check("Sin acceso total", REFERENCIA_HALLAZGOS["sin_acceso_total"], int(df_usuarios_crudo["DAYS_SINCE_ACCESS"].isna().sum()))

    id_sis = id_sis_compartidos(df_usuarios_crudo)
    _check("ID_SIS compartidos", REFERENCIA_HALLAZGOS["id_sis_compartidos"], id_sis["id_sis_compartidos"], tolerancia=5)
    _check(
        "Usuarios con ID_SIS compartido", REFERENCIA_HALLAZGOS["id_sis_usuarios_involucrados"],
        id_sis["usuarios_involucrados"], tolerancia=10,
    )
    return resultados
