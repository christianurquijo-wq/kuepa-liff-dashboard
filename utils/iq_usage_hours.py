"""
Capa de datos para la parte de IQ basada en `active_usage_hours` (BigQuery),
usada por Análisis dinámico / Detalle de consumo / Cobertura.

Por qué esto es distinto de utils/iq_data.py:
- iq_data.py lee 2 hojas de Google Sheets en vivo (usuarios y lecciones),
  actualizables por quien las llena.
- Esta tabla (`active_usage_hours`) no se pudo conectar en vivo: es
  demasiado grande para Sheets (1,19M+ filas, supera el límite de 10M
  celdas) y no hay acceso de cuenta de servicio al proyecto de BigQuery
  donde vive. La solución (acordada con Christian, sept-2026): Christian
  exporta la tabla fraccionada desde la consola de BigQuery con su propio
  usuario, y se agrega UNA VEZ (fuera de la app) a resúmenes chicos que sí
  caben en el repo como CSV -- no hay conexión en vivo a BigQuery ni a los
  Excel originales desde Streamlit. Actualizar estos números es repetir el
  proceso de exportación + agregación manual (ver README), no apretar un
  botón.

Dos familias de archivos en data/iq/usage_hours/:

A) mensual_alianza*.csv -- UN solo grano (mensual) por UNA sola dimensión
   cada uno (Rol, Grado, region_norm o app). Las usa Detalle_Consumo.py y
   no se tocan en este módulo salvo para leerlas tal cual.

B) detalle_<grano>.csv / totales_<grano>.csv, grano en
   {mensual, trimestral, semestral, anual} -- para Análisis dinámico.
   - totales_<grano>.csv: grano por Programa solamente. Usuarios_activos
     es un conteo EXACTO de usuarios únicos en ese período (calculado
     directo de las filas crudas, no sumando meses) -- se usa siempre que
     no hay filtro de Rol/Grado/Región (selección "Todos").
   - detalle_<grano>.csv: mismo grano pero además partido por Rol, Grado y
     region_norm. Al aplicar un filtro, la app SUMA usuarios_activos de las
     combinaciones que calzan -- esto es correcto si cada usuario cae en
     UN solo valor de esa dimensión por período (lo normal), pero puede
     sobre-contar si alguien aparece en más de un valor SELECCIONADO de la
     MISMA dimensión en el mismo período (ej. cambio de grado a mitad de
     año). Es una limitación conocida de trabajar con agregados estáticos
     en vez de las filas crudas en vivo -- se avisa en la propia página
     cuando aplica.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "iq" / "usage_hours"
FACTURADO_DIR = Path(__file__).resolve().parent.parent / "data" / "iq" / "facturado"

ALIANZA_A_SIGLA = {"IQ Primaria": "IQP", "IQ Secundaria": "IQS", "512": "IQ512"}
COLOR_PROGRAMA = {"IQP": "#29B6F6", "IQS": "#FD531E", "IQ512": "#2ECC71"}
ORDEN_PROGRAMA = ["IQP", "IQS", "IQ512"]

# oct-2026: el código interno del tercer programa sigue siendo "IQ512" --
# es el valor que ya viene así en los CSV que exporta Christian a mano
# (totales_*.csv/detalle_*.csv) y en la hoja de Sheets en vivo de
# utils/iq_data.py, así que tocar ese código obligaría a regenerar todo
# eso. Lo único que cambia es el nombre que VE el usuario: Christian
# aclaró que el programa en realidad se llama solo "512" (el "IQ" del
# código es un invento de una versión anterior del dashboard -- de hecho
# ALIANZA_A_SIGLA de arriba ya traduce el nombre real "512" a la sigla
# "IQ512"). PROGRAMA_LABEL se usa SOLO al mostrar algo en pantalla
# (multiselects, leyendas, tablas) -- nunca para filtrar/unir datos.
PROGRAMA_LABEL = {"IQP": "IQP", "IQS": "IQS", "IQ512": "512"}
COLOR_PROGRAMA_DISPLAY = {PROGRAMA_LABEL[k]: v for k, v in COLOR_PROGRAMA.items()}
ORDEN_PROGRAMA_DISPLAY = [PROGRAMA_LABEL[p] for p in ORDEN_PROGRAMA]


def etiqueta_programa(codigo: str) -> str:
    """Nombre para mostrar al usuario -- ver nota de PROGRAMA_LABEL arriba."""
    return PROGRAMA_LABEL.get(codigo, codigo)

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

GRANOS = {"Mes": "mensual", "Trimestre": "trimestral", "Semestre": "semestral", "Año": "anual"}
PERIOD_COLS = {
    "mensual": ["Anio", "Mes"],
    "trimestral": ["Anio", "Trimestre"],
    "semestral": ["Anio", "Semestre"],
    "anual": ["Anio"],
}


# ---------------------------------------------------------------------------
# A) Lectura legacy (Detalle de consumo) -- sin cambios de comportamiento
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def _leer_csv(nombre: str) -> pd.DataFrame:
    path = DATA_DIR / nombre
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "Alliance" in df.columns:
        df["Programa"] = df["Alliance"].map(ALIANZA_A_SIGLA).fillna(df["Alliance"])
    return df


@st.cache_data(ttl=3600)
def load_mensual_alianza() -> pd.DataFrame:
    return _leer_csv("mensual_alianza.csv")


@st.cache_data(ttl=3600)
def load_mensual_alianza_rol() -> pd.DataFrame:
    return _leer_csv("mensual_alianza_rol.csv")


@st.cache_data(ttl=3600)
def load_mensual_alianza_grado() -> pd.DataFrame:
    return _leer_csv("mensual_alianza_grado.csv")


@st.cache_data(ttl=3600)
def load_mensual_alianza_region() -> pd.DataFrame:
    return _leer_csv("mensual_alianza_region.csv")


@st.cache_data(ttl=3600)
def load_mensual_alianza_app() -> pd.DataFrame:
    return _leer_csv("mensual_alianza_app.csv")


@st.cache_data(ttl=3600)
def load_cobertura_ventanas() -> pd.DataFrame:
    return _leer_csv("cobertura_ventanas.csv")


@st.cache_data(ttl=3600)
def load_cobertura_huecos() -> pd.DataFrame:
    return _leer_csv("cobertura_huecos_confirmados.csv")


@st.cache_data(ttl=3600)
def load_regiones_educativas_coords() -> pd.DataFrame:
    """Coordenadas por Regional Educativa (MINERD) -- OJO: esto NO son las
    32 provincias oficiales de RD, son las ~18 sedes de las Regionales
    Educativas del Ministerio de Educación (con nombre de la ciudad sede),
    que es la taxonomía geográfica que realmente usa `regional_name` en
    `active_usage_hours`. Hay un archivo viejo (provincias_rd_coords.csv,
    provincias oficiales) que quedó sin usar por este motivo."""
    path = Path(__file__).resolve().parent.parent / "data" / "iq" / "regiones_educativas_coords.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def periodo_a_fecha(anio: int, mes: int):
    return pd.Timestamp(year=int(anio), month=int(mes), day=1)


def usage_hours_actualizado_al() -> str:
    """Última fecha con datos según cobertura_ventanas.csv (para mostrar
    'datos al DD/MM/AAAA' en vez de asumir que llega hasta hoy)."""
    vent = load_cobertura_ventanas()
    if vent.empty:
        return "sin datos"
    return pd.to_datetime(vent["hasta"]).max().strftime("%d/%m/%Y")


# ---------------------------------------------------------------------------
# B) Lectura multi-grano (Análisis dinámico)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def load_detalle(grano: str) -> pd.DataFrame:
    return _leer_csv(f"detalle_{grano}.csv")


@st.cache_data(ttl=3600)
def load_totales(grano: str) -> pd.DataFrame:
    return _leer_csv(f"totales_{grano}.csv")


def _orden(df: pd.DataFrame, grano: str) -> pd.Series:
    if grano == "mensual":
        return df["Anio"] * 12 + df["Mes"]
    if grano == "trimestral":
        return df["Anio"] * 4 + df["Trimestre"].str[1].astype(int)
    if grano == "semestral":
        return df["Anio"] * 2 + df["Semestre"].str[1].astype(int)
    return df["Anio"].astype(int)


def _label(row, grano: str) -> str:
    if grano == "mensual":
        return f"{MESES_ES[int(row['Mes']) - 1]} {int(row['Anio'])}"
    if grano == "trimestral":
        return f"T{row['Trimestre'][1]} {int(row['Anio'])}"
    if grano == "semestral":
        return f"S{row['Semestre'][1]} {int(row['Anio'])}"
    return str(int(row["Anio"]))


def etiquetar(df: pd.DataFrame, grano: str) -> pd.DataFrame:
    """Agrega columnas _orden (para ordenar cronológicamente) y _label
    (texto en español para mostrar), sin modificar el resto de columnas."""
    df = df.copy()
    df["_orden"] = _orden(df, grano)
    df["_label"] = df.apply(lambda r: _label(r, grano), axis=1)
    return df.sort_values("_orden").reset_index(drop=True)


@st.cache_data(ttl=3600)
def alianzas_disponibles() -> list:
    tot = load_totales("mensual")
    if tot.empty:
        return ORDEN_PROGRAMA
    presentes = set(tot["Programa"].unique())
    return [p for p in ORDEN_PROGRAMA if p in presentes]


@st.cache_data(ttl=3600)
def valores_dimension(dim: str) -> list:
    """dim en {'Rol', 'Grado', 'region_norm'} -- valores encontrados en el
    detalle mensual (son los mismos en cualquier grano, es la misma data
    de origen)."""
    det = load_detalle("mensual")
    if det.empty or dim not in det.columns:
        return []
    return sorted(det[dim].dropna().unique().tolist())


def hay_filtro_dimensional(rol_sel, grado_sel, region_sel) -> bool:
    return bool(rol_sel) or bool(grado_sel) or bool(region_sel)


def serie(grano: str, alianzas: list, rol_sel: list, grado_sel: list, region_sel: list) -> pd.DataFrame:
    """Devuelve una fila por (periodo, Programa) -- para gráficas que
    colorean por alianza. Usa totales_<grano> (exacto) si no hay filtro de
    Rol/Grado/Región; si hay, usa detalle_<grano> filtrado y re-agregado
    (con la limitación de sobre-conteo documentada arriba)."""
    cols = PERIOD_COLS[grano]
    if not hay_filtro_dimensional(rol_sel, grado_sel, region_sel):
        df = load_totales(grano)
        df = df[df["Programa"].isin(alianzas)]
        g = df.groupby(cols + ["Programa"], dropna=False).agg(
            usuarios_activos=("usuarios_activos", "sum"),
            horas_totales=("horas_totales", "sum"),
            registros=("registros", "sum"),
        ).reset_index()
        return etiquetar(g, grano)

    df = load_detalle(grano)
    df = df[df["Programa"].isin(alianzas)]
    if rol_sel:
        df = df[df["Rol"].isin(rol_sel)]
    if grado_sel:
        df = df[df["Grado"].isin(grado_sel)]
    if region_sel:
        df = df[df["region_norm"].isin(region_sel)]
    g = df.groupby(cols + ["Programa"], dropna=False).agg(
        usuarios_activos=("usuarios_activos", "sum"),
        horas_totales=("horas_totales", "sum"),
        registros=("registros", "sum"),
    ).reset_index()
    return etiquetar(g, grano)


def serie_total(grano: str, alianzas: list, rol_sel: list, grado_sel: list, region_sel: list) -> pd.DataFrame:
    """Igual que serie(), pero sumado a un solo valor por período (todas
    las alianzas/filtros seleccionados juntos) -- para el KPI de cabecera
    y la tabla de variación."""
    s = serie(grano, alianzas, rol_sel, grado_sel, region_sel)
    if s.empty:
        return s
    cols = PERIOD_COLS[grano]
    g = s.groupby(cols, dropna=False).agg(
        usuarios_activos=("usuarios_activos", "sum"),
        horas_totales=("horas_totales", "sum"),
        registros=("registros", "sum"),
    ).reset_index()
    return etiquetar(g, grano)


def agregar_comparaciones(df: pd.DataFrame, grano: str) -> pd.DataFrame:
    """Agrega, sobre una serie ya ordenada cronológicamente (salida de
    serie_total), las columnas de comparación: vs período inmediatamente
    anterior y vs mismo período del año anterior. En granularidad Año
    ambas comparaciones son la misma cosa (no hay 'sub-período')."""
    df = df.sort_values("_orden").reset_index(drop=True)
    df["usuarios_ant"] = df["usuarios_activos"].shift(1)
    df["horas_ant"] = df["horas_totales"].shift(1)

    sub_col = {"mensual": "Mes", "trimestral": "Trimestre", "semestral": "Semestre", "anual": None}[grano]
    if sub_col:
        idx_usr = df.set_index(["Anio", sub_col])["usuarios_activos"]
        idx_hrs = df.set_index(["Anio", sub_col])["horas_totales"]
        claves = list(zip(df["Anio"] - 1, df[sub_col]))
        df["usuarios_anio_ant"] = [idx_usr.get(k) for k in claves]
        df["horas_anio_ant"] = [idx_hrs.get(k) for k in claves]
    else:
        df["usuarios_anio_ant"] = df["usuarios_ant"]
        df["horas_anio_ant"] = df["horas_ant"]

    for base, cmp_col, out in [
        ("usuarios_activos", "usuarios_ant", "var_usuarios_ant_pct"),
        ("usuarios_activos", "usuarios_anio_ant", "var_usuarios_anio_pct"),
        ("horas_totales", "horas_ant", "var_horas_ant_pct"),
        ("horas_totales", "horas_anio_ant", "var_horas_anio_pct"),
    ]:
        df[out] = (df[base] - df[cmp_col]) / df[cmp_col].replace(0, pd.NA) * 100

    return df


def rango_fechas_periodo(grano: str, anio: int, sub) -> tuple:
    """(fecha_inicio, fecha_fin) del período -- para cruzar contra huecos
    de cobertura (que están en fechas de día)."""
    anio = int(anio)
    if grano == "mensual":
        mes = int(sub)
        inicio = pd.Timestamp(year=anio, month=mes, day=1)
        fin = inicio + pd.offsets.MonthEnd(0)
    elif grano == "trimestral":
        q = int(str(sub)[1])
        mes_inicio = (q - 1) * 3 + 1
        inicio = pd.Timestamp(year=anio, month=mes_inicio, day=1)
        fin = inicio + pd.offsets.QuarterEnd(0)
    elif grano == "semestral":
        s = int(str(sub)[1])
        mes_inicio = 1 if s == 1 else 7
        inicio = pd.Timestamp(year=anio, month=mes_inicio, day=1)
        fin = inicio + pd.DateOffset(months=6) - pd.DateOffset(days=1)
    else:
        inicio = pd.Timestamp(year=anio, month=1, day=1)
        fin = pd.Timestamp(year=anio, month=12, day=31)
    return inicio, fin


def huecos_en_rango(fecha_inicio, fecha_fin) -> pd.DataFrame:
    """Huecos confirmados que se solapan con [fecha_inicio, fecha_fin]."""
    huecos = load_cobertura_huecos()
    if huecos.empty:
        return huecos
    h = huecos.copy()
    h["desde"] = pd.to_datetime(h["desde"])
    h["hasta"] = pd.to_datetime(h["hasta"])
    return h[(h["desde"] <= fecha_fin) & (h["hasta"] >= fecha_inicio)]


# ---------------------------------------------------------------------------
# C) Facturado (Excel "Usuarios activos LMS - Proyectos Inicia.xlsx") --
#    Análisis dinámico, sección "Real vs. facturado"
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def load_facturado() -> pd.DataFrame:
    """Datos ESTÁTICOS de usuarios/horas facturados, extraídos a mano
    (oct-2026) de la hoja 'Global' del Excel de Christian ("Usuarios
    activos LMS - Proyectos Inicia.xlsx"), sumando las filas INDIVIDUALES
    por programa (IQP / IQS / i512, filas 4-6 = Activos y 10-12 = Horas),
    NO las filas agregadas 'TOTAL ACTIVOS' / 'TOTAL USO + ACTIVOS' -- esas
    agregadas vienen mal calculadas en el Excel (para varios meses dan
    justo la mitad de la suma de las 3 filas por programa; confirmado con
    Christian: el dato real de usuarios es la suma por programa, ej. marzo
    2026 = 53 (IQP) + 3818 (IQS) + 47 (i512) = 3918).

    Cobertura: 2024-03 a 2026-08 -- antes de marzo 2024 el Excel no tiene
    horas, y de septiembre 2026 en adelante los meses todavía no estaban
    llenados (0 en el Excel = sin dato, no un cero real), así que se
    excluyen en vez de graficarse como una caída a cero.

    No hay conexión en vivo a este Excel (es un archivo que Christian
    mantiene a mano) -- actualizar estos números es repetir la extracción
    manual, igual que con active_usage_hours (ver clase A arriba)."""
    path = FACTURADO_DIR / "facturado_mensual.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def serie_facturado(grano: str, alianzas: list) -> pd.DataFrame:
    """Igual forma de salida que serie_total() (Anio + columna de
    sub-período + _orden/_label), pero sobre los datos facturados. Ya
    viene sumado a un solo total (no hay Rol/Grado/Región en el Excel,
    solo Programa) -- por eso no existe una versión 'serie_facturado' con
    desglose por Programa, análoga a serie()."""
    df = load_facturado()
    if df.empty or not alianzas:
        return pd.DataFrame()
    df = df[df["Programa"].isin(alianzas)].copy()
    if df.empty:
        return df
    df["Trimestre"] = "Q" + (((df["Mes"] - 1) // 3) + 1).astype(str)
    df["Semestre"] = "S" + (((df["Mes"] - 1) // 6) + 1).astype(str)
    cols = PERIOD_COLS[grano]
    g = df.groupby(cols, dropna=False).agg(
        usuarios_facturados=("usuarios_facturados", "sum"),
        horas_facturados=("horas_facturados", "sum"),
    ).reset_index()
    return etiquetar(g, grano)
