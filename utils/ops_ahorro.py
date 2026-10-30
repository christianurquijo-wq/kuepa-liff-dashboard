"""
Ahorro de tiempo de las automatizaciones (pandas; leer_historico lee el Sheet).

Regla (aprobada por Christian, oct-2026):
  - Cada automatización del CATALOGO tiene `min_ahorro_ejecucion`: minutos de trabajo manual que
    reemplaza UNA ejecución exitosa. Vacío = sin estimar (no suma); 0 = no ahorra (lotes, que se
    cuentan por script, e infraestructura).
  - Solo suman las ejecuciones EXITOSAS.
  - `tope_ejecuciones_dia`: máximo de ejecuciones por día y automatización que suman (si un flujo
    corre 10 veces al día pero a mano se haría 1 vez, solo cuenta 1). Vacío = sin tope.
  - Fuentes: LOG_EJECUCIONES (bitácora desde oct-2026) + LOG_HISTORICO (historial reconstruido
    desde GitHub Actions y n8n con _reorg/ops_historial_ahorro.py). Se deduplica por id_ejecucion.
  - Solo horas (sin valor en dinero). Jornada = 8 h; FTE = horas ÷ (días hábiles del rango × 8).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from utils.ops_metrics import ORIGEN_GRUPO, _nombre_respaldo

HORAS_JORNADA = 8
PERIODOS = ["Día", "Semana", "Mes", "Trimestre", "Semestre", "Año"]
ESTADO_SIN = "Sin estimar"
# Scripts de infraestructura que corren en los lotes pero no reemplazan trabajo del equipo
# (no tienen fila en el CATALOGO): cuentan 0 en vez de aparecer como "sin estimar".
INFRA = {"Vigencia_sandbox.py", "Foto_diaria_EFE.py", "ops_sync_n8n.py", "ops_logger.py"}


@st.cache_data(ttl=600, show_spinner=False)
def leer_historico() -> pd.DataFrame:
    """Pestaña LOG_HISTORICO (mismo formato que LOG_EJECUCIONES). Si no existe: vacío."""
    from utils.ops_data import TZ, _hoja

    try:
        valores = _hoja("LOG_HISTORICO").get_all_values()
    except Exception:  # noqa: BLE001 -- la pestaña es opcional
        return pd.DataFrame()
    if len(valores) <= 1:
        return pd.DataFrame(columns=valores[0] if valores else [])
    df = pd.DataFrame(valores[1:], columns=valores[0])
    df = df[df["id_ejecucion"] != ""].copy()
    for c in ("fecha_inicio", "fecha_fin"):
        df[c] = pd.to_datetime(df[c], errors="coerce", utc=True).dt.tz_convert(TZ)
    df["duracion_seg"] = pd.to_numeric(df["duracion_seg"], errors="coerce")
    df["automatizacion_id"] = df["automatizacion_id"].str.replace(r"^[^/:]+/", "", regex=True)
    return df.dropna(subset=["fecha_inicio"])


def _num(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie.astype(str).str.strip().str.replace(",", "."), errors="coerce")


def preparar(log: pd.DataFrame, historico: pd.DataFrame, catalogo: pd.DataFrame) -> pd.DataFrame:
    """Una fila por ejecución, con los minutos que aporta (0 si no suma) y por qué."""
    partes = [x.assign(fuente=f) for x, f in ((log, "Bitácora"), (historico, "Historial reconstruido"))
              if x is not None and not x.empty]
    if not partes:
        return pd.DataFrame()
    df = pd.concat(partes, ignore_index=True)
    df = df.sort_values("fuente").drop_duplicates("id_ejecucion", keep="first")  # la bitácora manda
    df = df.sort_values("fecha_inicio").reset_index(drop=True)

    cols = ["nombre", "proyecto", "responsable", "min_ahorro_ejecucion", "tope_ejecuciones_dia", "ahorro_estado",
            "periodicidad"]
    cat = catalogo.copy()
    for c in cols:
        if c not in cat:
            cat[c] = ""
    mapa = cat.drop_duplicates("automatizacion_id").set_index("automatizacion_id")[cols]
    df = df.join(mapa, on="automatizacion_id")
    # Igual que el resto de Operaciones: solo automatizaciones del CATALOGO (sin flujos "sin ficha").
    if not cat.empty:
        df = df[df["automatizacion_id"].isin(set(cat["automatizacion_id"]))].copy()
        if df.empty:
            return df

    df["en_catalogo"] = df["nombre"].notna()
    sin_nombre = df["nombre"].isna() | df["nombre"].astype(str).str.strip().eq("")
    df.loc[sin_nombre, "nombre"] = df[sin_nombre].apply(_nombre_respaldo, axis=1)
    df["proyecto"] = df["proyecto"].fillna("Sin catálogo").replace("", "Sin catálogo")
    df["responsable"] = df["responsable"].fillna("").replace("", "Sin responsable")
    df["periodicidad"] = df["periodicidad"].fillna("").replace("", "Sin dato")
    df["min_unit"] = _num(df["min_ahorro_ejecucion"].fillna(""))
    infra = df["script"].astype(str).isin(INFRA) & ~df["en_catalogo"]
    df.loc[infra, "min_unit"] = 0.0
    df["tope"] = _num(df["tope_ejecuciones_dia"].fillna(""))
    estado = df["ahorro_estado"].fillna("").astype(str).str.strip()
    df["ahorro_estado"] = np.where(df["min_unit"].isna(), ESTADO_SIN, estado.replace("", "Estimado"))
    df.loc[infra, "ahorro_estado"] = "Infraestructura"
    df["origen_grupo"] = df["origen"].map(ORIGEN_GRUPO).fillna("Manual / otra")
    df["exito"] = df["estado"].eq("EXITOSO")
    df["dia"] = df["fecha_inicio"].dt.tz_localize(None).dt.normalize() if df["fecha_inicio"].dt.tz is not None \
        else df["fecha_inicio"].dt.normalize()

    # Orden de la ejecución exitosa dentro del día (para aplicar el tope)
    df["n_dia"] = np.nan
    ok = df["exito"]
    df.loc[ok, "n_dia"] = df[ok].groupby(["automatizacion_id", "dia"]).cumcount() + 1

    df["motivo"] = "Suma"
    df.loc[~df["exito"], "motivo"] = "No exitosa"
    df.loc[df["exito"] & df["min_unit"].isna(), "motivo"] = ESTADO_SIN
    df.loc[df["exito"] & df["min_unit"].eq(0), "motivo"] = "No ahorra (0 min)"
    sobre_tope = df["exito"] & df["tope"].notna() & (df["n_dia"] > df["tope"])
    df.loc[sobre_tope & df["min_unit"].gt(0), "motivo"] = "Sobre el tope diario"
    df["minutos"] = np.where(df["motivo"].eq("Suma"), df["min_unit"], 0.0)
    df["horas"] = df["minutos"] / 60
    return df


def periodo(dias: pd.Series, granularidad: str) -> pd.Series:
    d = pd.to_datetime(dias)
    if granularidad == "Día":
        return d
    if granularidad == "Semana":
        return d - pd.to_timedelta(d.dt.weekday, unit="D")
    if granularidad == "Mes":
        return d.dt.to_period("M").dt.start_time
    if granularidad == "Trimestre":
        return d.dt.to_period("Q").dt.start_time
    if granularidad == "Semestre":
        return pd.to_datetime({"year": d.dt.year, "month": np.where(d.dt.month <= 6, 1, 7), "day": 1})
    return d.dt.to_period("Y").dt.start_time


def etiqueta(p: pd.Series, granularidad: str) -> pd.Series:
    if granularidad == "Día":
        return p.dt.strftime("%d/%m/%Y")
    if granularidad == "Semana":
        return "Sem " + p.dt.strftime("%d/%m/%Y")
    if granularidad == "Mes":
        return p.dt.strftime("%Y-%m")
    if granularidad == "Trimestre":
        return p.dt.year.astype(str) + "-T" + p.dt.quarter.astype(str)
    if granularidad == "Semestre":
        return p.dt.year.astype(str) + "-S" + np.where(p.dt.month <= 6, "1", "2")
    return p.dt.year.astype(str)


def dias_habiles(desde: pd.Timestamp, hasta: pd.Timestamp) -> int:
    return int(np.busday_count(desde.date(), (hasta + pd.Timedelta(days=1)).date()))


def kpis(df: pd.DataFrame, desde: pd.Timestamp, hasta: pd.Timestamp) -> dict:
    horas = float(df["horas"].sum())
    habiles = max(dias_habiles(desde, hasta), 1)
    return {
        "horas": horas,
        "jornadas": horas / HORAS_JORNADA,
        "fte": horas / (habiles * HORAS_JORNADA),
        "ejecuciones_suman": int(df["motivo"].eq("Suma").sum()),
        "exitosas": int(df["exito"].sum()),
        "automatizaciones": int(df.loc[df["motivo"].eq("Suma"), "automatizacion_id"].nunique()),
        "sin_estimar": int(df.loc[df["motivo"].eq(ESTADO_SIN), "automatizacion_id"].nunique()),
    }


def por_periodo(df: pd.DataFrame, granularidad: str, color: str | None = None) -> pd.DataFrame:
    x = df.assign(Periodo=periodo(df["dia"], granularidad))
    claves = ["Periodo"] + ([color] if color else [])
    out = x.groupby(claves, as_index=False)["horas"].sum().sort_values("Periodo")
    out["Etiqueta"] = etiqueta(out["Periodo"], granularidad)
    return out


def ranking(df: pd.DataFrame, por: str) -> pd.DataFrame:
    g = df.groupby(por).agg(horas=("horas", "sum"), ejecuciones=("motivo", lambda s: int(s.eq("Suma").sum())))
    return g[g["horas"] > 0].sort_values("horas", ascending=False).reset_index()


def tabla_automatizaciones(df: pd.DataFrame) -> pd.DataFrame:
    g = (df.groupby(["automatizacion_id", "nombre", "proyecto"], dropna=False)
         .agg(ejecuciones=("estado", "size"), exitosas=("exito", "sum"),
              suman=("motivo", lambda s: int(s.eq("Suma").sum())),
              sobre_tope=("motivo", lambda s: int(s.eq("Sobre el tope diario").sum())),
              min_ejecucion=("min_unit", "first"), tope=("tope", "first"),
              estado=("ahorro_estado", "first"), periodicidad=("periodicidad", "first"),
              horas=("horas", "sum"))
         .reset_index().sort_values("horas", ascending=False))
    g = g.drop(columns="automatizacion_id")
    return g[["nombre", "proyecto", "periodicidad"] + [c for c in g.columns if c not in ("nombre", "proyecto", "periodicidad")]]


def matriz(df: pd.DataFrame, granularidad: str, filas: str = "proyecto") -> pd.DataFrame:
    """Horas por proyecto (filas) x periodo (columnas), con total."""
    x = df.assign(Periodo=periodo(df["dia"], granularidad))
    t = x.pivot_table(index=filas, columns="Periodo", values="horas", aggfunc="sum", fill_value=0)
    t = t.reindex(sorted(t.columns), axis=1)
    t.columns = etiqueta(pd.Series(t.columns), granularidad).tolist()
    t["Total"] = t.sum(axis=1)
    return t[t["Total"] > 0].sort_values("Total", ascending=False).round(1)
