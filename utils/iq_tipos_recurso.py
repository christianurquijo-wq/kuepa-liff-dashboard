"""
IQ / Tipos de recurso -- datos y métricas de la página pages/iq/6_Tipos_de_Recurso.py

Fuente: tres CSV agregados en data/iq/tipos_recursos/agregados/, generados por
scripts/build_tipos_recurso.py a partir de los xlsx de BigQuery ("Tipos de
recurso IQS/IQP"). Los CSV NO traen datos personales (sin usuario, nombre ni
correo): son seguros para el repo. Costo de infraestructura: cero (se leen
del repo, sin BigQuery ni Google Sheets).

Definiciones (idénticas a las del PPTX de la reunión INICIA/MINERD 22/10/2026):
  * Periodo académico = 1-ago a 31-jul (ej. 2025-26 = ago-2025 a jul-2026).
  * Consumo = intento único (diagnóstico / simulacro / ejercitación; las
    reaperturas del mismo intento no cuentan) o vista de componente
    (video / editor / juego / otros).
  * Base depurada: se excluyen cuentas con >500 registros en un programa y
    periodo (cuentas atípicas/automáticas). Ver recursos_conciliacion.csv.
  * Finalización = grupos (usuario, componente, día) con >=1 intento
    'ended' / grupos de intentos. Solo diagnóstico, simulacro, ejercitación.
  * Puntaje = promedio de los intentos terminados con score (0-100).
  * Usuarios únicos NO se suman entre cortes: se leen del retículo
    precalculado (recursos_usuarios_unicos.csv) y solo se muestran cuando cada
    filtro está en 'todos' o en un único valor -- ver `usuarios_unicos`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "iq" / "tipos_recursos" / "agregados"

TIPOS = ["Simulacro", "Ejercitación", "Diagnóstico", "Video", "Editor", "Juego", "Otros"]
TIPOS_INTENTO = ["Diagnóstico", "Simulacro", "Ejercitación"]
GRADOS = ["1°", "2°", "3°", "4°", "5°", "6°", "Sin dato"]
MESES_ACAD = [8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7]  # año académico ago -> jul
MES_LABEL = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun", 7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"}
MES_ORDEN = [MES_LABEL[m] for m in MESES_ACAD]

COLOR_TIPO = {
    "Simulacro": "#FD531E",
    "Ejercitación": "#2ECC71",
    "Diagnóstico": "#29B6F6",
    "Video": "#F5B942",
    "Editor": "#A78BFA",
    "Juego": "#F78FB3",
    "Otros": "#8C8C8C",
}
COLOR_PROG = {"IQ Secundaria": "#FD531E", "IQ Primaria": "#29B6F6"}

SIN_CENTRO = "Sin centro identificado"


# ---------------------------------------------------------------- carga ----
@st.cache_data(ttl=3600, show_spinner="Cargando tipos de recurso...")
def load_cubo() -> pd.DataFrame:
    p = DATA_DIR / "recursos_cubo.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p)
    for c in ["prog", "periodo", "tipo", "grado", "region", "area", "rol"]:
        df[c] = df[c].astype("category")
    df["mes_label"] = pd.Categorical(df["mes"].map(MES_LABEL), categories=MES_ORDEN, ordered=True)
    return df


@st.cache_data(ttl=3600)
def load_unicos() -> pd.DataFrame:
    p = DATA_DIR / "recursos_usuarios_unicos.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


@st.cache_data(ttl=3600)
def load_conciliacion() -> pd.DataFrame:
    p = DATA_DIR / "recursos_conciliacion.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def tipos_en_orden(valores) -> list[str]:
    s = set(valores)
    return [t for t in TIPOS if t in s] + sorted(s - set(TIPOS))


def grados_en_orden(valores) -> list[str]:
    s = set(valores)
    return [g for g in GRADOS if g in s] + sorted(s - set(GRADOS))


def periodos_info(cubo: pd.DataFrame) -> pd.DataFrame:
    """Meses con datos por periodo -> marca incompleto (<12 meses)."""
    x = cubo.groupby("periodo", observed=True)["mes"].nunique().rename("meses").reset_index()
    x["completo"] = x["meses"] >= 12
    return x.sort_values("periodo").reset_index(drop=True)


# ------------------------------------------------------------- formatos ----
def fmt_int(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{int(round(x)):,}".replace(",", ".")


def fmt_dec(x, dec: int = 1) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{x:,.{dec}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def fmt_pct(x, dec: int = 1, signo: bool = False) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    s = f"{x:+.{dec}f}" if signo else f"{x:.{dec}f}"
    return s.replace(".", ",") + "%"


def fmt_pts(x, dec: int = 1) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return (f"{x:+.{dec}f}").replace(".", ",") + " pts"


def var_pct(nuevo, viejo) -> float:
    if viejo is None or nuevo is None or pd.isna(viejo) or pd.isna(nuevo) or viejo == 0:
        return np.nan
    return (nuevo - viejo) / viejo * 100


def delta_html(texto: str, positivo: bool | None) -> str:
    color = "#9A9A9A" if positivo is None else ("#2ECC71" if positivo else "#E74C3C")
    flecha = "" if positivo is None else ("▲ " if positivo else "▼ ")
    return f"<span style='color:{color}; font-weight:600;'>{flecha}{texto}</span>"


# ------------------------------------------------------------- métricas ----
def filtrar(
    cubo: pd.DataFrame,
    periodos=None, progs=None, tipos=None, grados=None, regiones=None, areas=None, roles=None,
) -> pd.DataFrame:
    m = pd.Series(True, index=cubo.index)
    for col, sel in [("periodo", periodos), ("prog", progs), ("tipo", tipos), ("grado", grados),
                     ("region", regiones), ("area", areas), ("rol", roles)]:
        if sel is not None:
            m &= cubo[col].isin(list(sel))
    return cubo[m]


def resumen(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Consumos, finalización (%) y puntaje medio agregados por las columnas `by`."""
    g = df.groupby(by, observed=True)[["consumos", "grupos", "grupos_fin", "intentos_terminados", "n_con_puntaje", "suma_puntaje"]].sum().reset_index()
    g["finalizacion"] = np.where(g["grupos"] > 0, g["grupos_fin"] / g["grupos"].replace(0, np.nan) * 100, np.nan)
    g["puntaje"] = np.where(g["n_con_puntaje"] > 0, g["suma_puntaje"] / g["n_con_puntaje"].replace(0, np.nan), np.nan)
    return g


def totales_periodo(df: pd.DataFrame, periodo: str) -> dict:
    z = df[df["periodo"] == periodo]
    g = z["grupos"].sum()
    npunt = z["n_con_puntaje"].sum()
    return {
        "consumos": float(z["consumos"].sum()),
        "finalizacion": float(z["grupos_fin"].sum() / g * 100) if g else np.nan,
        "puntaje": float(z["suma_puntaje"].sum() / npunt) if npunt else np.nan,
    }


def usuarios_unicos(
    unicos: pd.DataFrame, periodo: str, progs: list[str],
    sel: dict[str, list[str]], universo: dict[str, list[str]],
) -> int | None:
    """
    Usuarios únicos exactos para `periodo`, o None si la combinación de
    filtros no está precalculada.

    sel / universo: {'tipo','grado','area','rol','region'} -> valores elegidos / todos
    los valores posibles. Cada dimensión debe estar en 'todos' (-> 'Todos') o en
    un único valor. Regional solo se combina con tipo (no con grado/área/rol).
    Con 2 programas se suman (IQP e IQS casi no comparten usuarios).
    """
    if unicos.empty:
        return None
    clave = {}
    for dim in ("tipo", "grado", "area", "rol", "region"):
        elegidos, todos = set(sel[dim]), set(universo[dim])
        if elegidos == todos:
            clave[dim] = "Todos"
        elif len(elegidos) == 1:
            clave[dim] = next(iter(elegidos))
        else:
            return None
    if clave["region"] != "Todos" and any(clave[d] != "Todos" for d in ("grado", "area", "rol")):
        return None
    total = 0
    for prog in progs:
        z = unicos[(unicos["prog"] == prog) & (unicos["periodo"] == periodo) & (unicos["mes"] == 0)]
        for dim, val in clave.items():
            z = z[z[dim] == val]
        total += int(z["usuarios"].sum())  # sin fila = 0 usuarios
    return total
