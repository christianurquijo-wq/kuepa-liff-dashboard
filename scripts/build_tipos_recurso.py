"""
Genera los agregados de la página IQ > Tipos de recurso a partir de los xlsx
crudos exportados de BigQuery ("Tipos de recurso IQS-*.xlsx", "Tipo de recurso
IQP.xlsx", "...IQP-BV.xlsx", etc.).

Los xlsx crudos traen NOMBRE y CORREO de estudiantes -> NUNCA se suben al repo
(ver .gitignore). Este script los descarta al leer: solo las columnas de abajo
llegan a memoria y a los agregados.

Uso (desde la raíz del repo, con el venv activo):

    python scripts/build_tipos_recurso.py
    python scripts/build_tipos_recurso.py --src data/iq/tipos_recursos --out data/iq/tipos_recursos/agregados

Requiere pandas + openpyxl (ya en requirements.txt). Si está instalado
`python-calamine` (pip install python-calamine) la lectura de los xlsx es
~10x más rápida; sin él puede tardar varios minutos con ~265 MB de xlsx.

Salidas (data/iq/tipos_recursos/agregados/):
  recursos_cubo.csv            cubo principal: prog x periodo x mes x tipo x grado x
                               regional x área x rol -> consumos, grupos, grupos_fin,
                               intentos_terminados, n_con_puntaje, suma_puntaje
  recursos_usuarios_unicos.csv usuarios únicos (no sumables) por combinación de
                               tipo/grado/área/rol (+ regional y mes por separado)
  recursos_conciliacion.csv    registros brutos -> sin reaperturas -> base depurada

Reglas de depuración (idénticas a las del PPTX de la reunión del 22/10/2026):
  * Periodo académico = 1-ago a 31-jul.
  * "Consumo" = intento único (diagnóstico/simulacro/ejercitación: clave
    usuario+componente+día+puntaje+estado, las reaperturas no cuentan) o vista
    de componente (video/editor/juego/otros).
  * Base depurada = excluye cuentas con >500 registros en un mismo programa y
    periodo (cuentas atípicas/automáticas).
  * Finalización = % de grupos (usuario, componente, día) con >=1 intento
    'ended', solo diagnóstico/simulacro/ejercitación.
  * Puntaje = promedio de intentos terminados con score.
  * Área de simulacros/diagnósticos se deriva del nombre del recurso (venía
    mal etiquetada: Sociales aparecía como Naturaleza).
  * BAORUCO -> BAHORUCO; "USUARIO SIN CENTRO"/vacío -> "Sin centro identificado".
"""
from __future__ import annotations

import argparse
import itertools
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROG_LABEL = {"IQS": "IQ Secundaria", "IQP": "IQ Primaria"}
TIPOS_INTENTO = ["Diagnóstico", "Simulacro", "Ejercitación"]
TIPOS_CONOCIDOS = TIPOS_INTENTO + ["Video", "Editor", "Juego"]
AREAS_VALIDAS = ("Matemáticas", "Lengua Española", "Ciencias de la Naturaleza", "Ciencias Sociales")
UMBRAL_ATIPICAS = 500  # registros por usuario, programa y periodo

# Solo estas columnas se leen del xlsx (NOMBRE/CORREO quedan fuera a propósito).
COLUMNAS = [
    "user_id", "fecha", "status", "academic_component_id", "resource_name",
    "roles_string", "REGION", "Alliance", "origen", "GRADO", "knowledge_area_name",
    "score", "Tipo_recurso", "Leccion_asociada",
]


def leer_xlsx(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_excel(path, engine="calamine", dtype=str, usecols=COLUMNAS)
    except ImportError:
        df = pd.read_excel(path, engine="openpyxl", dtype=str, usecols=COLUMNAS)
    return df


def cargar(src: Path) -> pd.DataFrame:
    archivos = sorted(p for p in src.glob("*.xlsx") if not p.name.startswith("~$"))
    if not archivos:
        sys.exit(f"No encontré .xlsx en {src}")
    partes = []
    for p in archivos:
        df = leer_xlsx(p)
        print(f"  {p.name}: {len(df):,} filas")
        partes.append(df)
    return pd.concat(partes, ignore_index=True)


def _grado(x) -> str:
    if pd.isna(x):
        return "Sin dato"
    m = re.match(r"\s*(\d)", str(x))
    return f"{m.group(1)}°" if m else "Sin dato"


def _area(tipo, recurso, area_raw) -> str:
    if tipo in ("Simulacro", "Diagnóstico"):
        r = str(recurso).lower()
        if "matem" in r:
            return "Matemáticas"
        if "lengua" in r:
            return "Lengua Española"
        if "sociales" in r:
            return "Ciencias Sociales"
        if "naturaleza" in r:
            return "Ciencias de la Naturaleza"
        return "Otras / sin dato"
    ar = str(area_raw) if pd.notna(area_raw) else "Sin información"
    ar = re.sub(r"\s*-\s*\d°\s*$", "", ar)
    ar = re.sub(r"\s*-\s*\d(er|do|to|mo|vo)? grado$", "", ar).strip()
    return ar if ar in AREAS_VALIDAS else "Otras / sin dato"


def preparar(a: pd.DataFrame) -> pd.DataFrame:
    """Tipifica, normaliza y marca cons / atip / dep. Idempotente sobre datos ya tipados."""
    a = a.copy()
    a["f"] = pd.to_datetime(a["fecha"].astype(str).str[:19], errors="coerce").dt.normalize()
    a = a[a["f"].notna()].copy()
    a["score"] = pd.to_numeric(a["score"], errors="coerce")
    a["prog"] = np.where(a["Alliance"] == "IQ Primaria", "IQP", "IQS")
    a["grado"] = a["GRADO"].map(_grado)
    a["region"] = (
        a["REGION"].fillna("").astype(str).str.strip().str.upper()
        .replace({"": "Sin centro identificado", "USUARIO SIN CENTRO": "Sin centro identificado", "BAORUCO": "BAHORUCO"})
    )
    a["rol"] = a["roles_string"].fillna("Sin dato")
    a["recurso"] = a["Leccion_asociada"].fillna(a["resource_name"])
    mn, yr = a["f"].dt.month, a["f"].dt.year
    a["periodo"] = np.where(
        mn >= 8,
        yr.astype(str) + "-" + (yr + 1).astype(str).str[2:],
        (yr - 1).astype(str) + "-" + yr.astype(str).str[2:],
    )
    m = a[["Tipo_recurso", "recurso", "knowledge_area_name"]].drop_duplicates().copy()
    m["area"] = [_area(t, r, k) for t, r, k in zip(m["Tipo_recurso"], m["recurso"], m["knowledge_area_name"])]
    a = a.merge(m, on=["Tipo_recurso", "recurso", "knowledge_area_name"], how="left")
    a["tipo"] = np.where(a["Tipo_recurso"].isin(TIPOS_CONOCIDOS), a["Tipo_recurso"], "Otros")

    att = a["origen"] == "attempts"
    key = (
        a["user_id"].astype(str) + "|" + a["academic_component_id"].fillna("").astype(str) + "|"
        + a["f"].astype(str) + "|" + a["score"].fillna(-1).astype(str) + "|" + a["status"].fillna("")
    )
    a["att"] = att
    a["cons"] = (~att) | (att & ~key.duplicated())
    n = a.groupby(["prog", "periodo", "user_id"])["user_id"].transform("size")
    a["atip"] = n > UMBRAL_ATIPICAS
    a["dep"] = a["cons"] & ~a["atip"]
    a["fin"] = (att & (a["status"] == "ended") & a["tipo"].isin(TIPOS_INTENTO)).astype(int)
    a["sc_ok"] = att & (a["status"] == "ended") & a["score"].notna() & a["tipo"].isin(TIPOS_INTENTO)
    a["mes"] = a["f"].dt.month
    a["anio"] = a["f"].dt.year
    return a


DIMS = ["prog", "periodo", "anio", "mes", "tipo", "grado", "region", "area", "rol"]


def cubo(a: pd.DataFrame) -> pd.DataFrame:
    d = a[a["dep"]]
    c = d.groupby(DIMS).agg(
        consumos=("dep", "size"),
        intentos_terminados=("fin", "sum"),
        n_con_puntaje=("sc_ok", "sum"),
    ).reset_index()
    sp = d[d["sc_ok"]].groupby(DIMS)["score"].sum()
    c["suma_puntaje"] = sp.reindex(pd.MultiIndex.from_frame(c[DIMS])).fillna(0).values

    # Finalización: grupos (usuario, componente, día) de intentos, sin cuentas atípicas.
    g = a[a["att"] & ~a["atip"] & a["tipo"].isin(TIPOS_INTENTO)]
    gk = ["prog", "periodo", "user_id", "academic_component_id", "f"]
    gg = g.groupby(gk).agg(
        anio=("anio", "first"), mes=("mes", "first"), tipo=("tipo", "first"), grado=("grado", "first"),
        region=("region", "first"), area=("area", "first"), rol=("rol", "first"),
        ended=("status", lambda s: bool((s == "ended").any())),
    ).reset_index()
    gc = gg.groupby(DIMS).agg(grupos=("ended", "size"), grupos_fin=("ended", "sum")).reset_index()
    c = c.merge(gc, on=DIMS, how="outer")
    for col in ["consumos", "intentos_terminados", "n_con_puntaje", "suma_puntaje", "grupos", "grupos_fin"]:
        c[col] = c[col].fillna(0)
    for col in ["consumos", "intentos_terminados", "n_con_puntaje", "grupos", "grupos_fin"]:
        c[col] = c[col].astype("int64")
    c["prog"] = c["prog"].map(PROG_LABEL)
    c["suma_puntaje"] = c["suma_puntaje"].round(1)
    return c[DIMS + ["consumos", "grupos", "grupos_fin", "intentos_terminados", "n_con_puntaje", "suma_puntaje"]]


def unicos(a: pd.DataFrame) -> pd.DataFrame:
    """Usuarios únicos (distintos) sobre la base depurada.

    Los únicos no se suman entre celdas. Se precalcula el 'retículo' completo
    de tipo x grado x área x rol: cada columna vale un valor concreto o 'Todos'
    (= marginalizada), de modo que la página puede mostrar únicos exactos
    cuando cada filtro está en 'todos' o en un solo valor. Regional y mes se
    cruzan solo con tipo (no con grado/área/rol) para no explotar el tamaño.
    """
    d = a[a["dep"]]
    base = ["prog", "periodo"]
    otros = {"tipo": "Todos", "grado": "Todos", "area": "Todos", "rol": "Todos", "region": "Todos", "mes": 0}
    filas = []
    dims4 = ["tipo", "grado", "area", "rol"]
    for k in range(len(dims4) + 1):
        for sub in itertools.combinations(dims4, k):
            g = d.groupby(base + list(sub))["user_id"].nunique().reset_index(name="usuarios")
            for col, val in otros.items():
                if col not in sub:
                    g[col] = val
            filas.append(g)
    for dim in ("region", "mes"):
        for sub in ([dim], [dim, "tipo"]):
            g = d.groupby(base + sub)["user_id"].nunique().reset_index(name="usuarios")
            for col, val in otros.items():
                if col not in sub:
                    g[col] = val
            filas.append(g)
    u = pd.concat(filas, ignore_index=True)
    u["mes"] = u["mes"].astype(int)
    u["prog"] = u["prog"].map(PROG_LABEL)
    cols = ["prog", "periodo", "tipo", "grado", "area", "rol", "region", "mes", "usuarios"]
    return u[cols].drop_duplicates(subset=cols[:-1]).sort_values(cols[:-1]).reset_index(drop=True)


def conciliacion(a: pd.DataFrame) -> pd.DataFrame:
    r = a.groupby(["prog", "periodo"]).agg(
        registros_brutos=("cons", "size"),
        sin_revisiones=("cons", "sum"),
        base_depurada=("dep", "sum"),
    )
    r["usuarios_depurada"] = a[a["dep"]].groupby(["prog", "periodo"])["user_id"].nunique()
    r["cuentas_atipicas"] = a[a["atip"]].groupby(["prog", "periodo"])["user_id"].nunique()
    r = r.fillna(0).astype("int64").reset_index()
    r["prog"] = r["prog"].map(PROG_LABEL)
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=str(ROOT / "data" / "iq" / "tipos_recursos"))
    ap.add_argument("--out", default=str(ROOT / "data" / "iq" / "tipos_recursos" / "agregados"))
    args = ap.parse_args()
    src, out = Path(args.src), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print("Leyendo xlsx...")
    raw = cargar(src)
    print("Depurando...")
    a = preparar(raw)
    del raw
    for nombre, df in (("recursos_cubo", cubo(a)), ("recursos_usuarios_unicos", unicos(a)), ("recursos_conciliacion", conciliacion(a))):
        p = out / f"{nombre}.csv"
        df.to_csv(p, index=False, encoding="utf-8")
        print(f"  {p.name}: {len(df):,} filas, {p.stat().st_size / 1e6:.2f} MB")
    print("Listo. Revisa recursos_conciliacion.csv y haz commit SOLO de la carpeta agregados/.")


if __name__ == "__main__":
    main()
