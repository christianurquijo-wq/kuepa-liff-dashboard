"""
Regenera los agregados de data/iq/usage_hours/ (Análisis dinámico, Detalle de consumo, Cobertura) a partir de
los exportes crudos de BigQuery `active_usage_hours` ("Active_usage_hours_2026-1.xlsx", ...).

Los exportes crudos traen IDs de usuario y centro educativo: viven en data/iq/usage_hours/crudo/ (en
.gitignore) y NUNCA se suben al repo; solo se suben los CSV agregados.

Uso (desde la raíz del repo, con el venv activo):

    python scripts/build_usage_hours.py
    python scripts/build_usage_hours.py --crudo data/iq/usage_hours/crudo --out data/iq/usage_hours

Cómo funciona:
  * Se reemplazan SOLO los años que aparecen en los exportes (p. ej. 2026); los años anteriores de los CSV se
    conservan tal cual. Como los usuarios únicos no se suman entre meses, cada año a recalcular debe venir
    COMPLETO (desde el 1 de enero): si el exporte de un año empieza después, el script se detiene.
  * Reglas (calibradas contra los CSV de sept-2026: coinciden exacto en registros, usuarios y horas):
      - fecha del evento = created_at (UTC); año/mes/trimestre/semestre salen de ahí.
      - se elimina duplicado por `_id` (los exportes partidos se solapan en los bordes).
      - horas = suma de time_view (segundos) / 3600, redondeado a 1 decimal.
      - usuarios_activos = usuarios distintos (`user`) en el periodo -> exacto en totales_*; en detalle_* es por
        combinación Rol x Grado x Región (ver docstring de utils/iq_usage_hours.py).
      - Rol vacío -> "Sin rol" (en mensual_alianza_rol queda vacío, como siempre); Grado vacío -> "No especificado".
      - Región: regional_name en mayúsculas y sin tildes, BAORUCO -> BAHORUCO; vacío o "USUARIO SIN CENTRO" ->
        "Sin ubicación".
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SIGLA = {"IQ Primaria": "IQP", "IQ Secundaria": "IQS", "512": "IQ512"}
COLS = ["_id", "app", "user", "time_view", "created_at", "roles_string", "regional_name", "Alliance", "Grado"]
MET = ["usuarios_activos", "horas_totales", "registros"]


def leer(crudo: Path) -> pd.DataFrame:
    archivos = sorted(p for p in crudo.iterdir() if p.suffix.lower() in (".xlsx", ".csv") and not p.name.startswith("~$"))
    if not archivos:
        sys.exit(f"No encontré exportes .xlsx/.csv en {crudo}")
    partes = []
    for p in archivos:
        if p.suffix.lower() == ".csv":
            df = pd.read_csv(p, dtype=str, usecols=lambda c: c in COLS)
        else:
            try:
                df = pd.read_excel(p, engine="calamine", dtype=str, usecols=lambda c: c in COLS)
            except ImportError:
                df = pd.read_excel(p, engine="openpyxl", dtype=str, usecols=lambda c: c in COLS)
        faltan = set(COLS) - set(df.columns)
        if faltan:
            sys.exit(f"{p.name}: faltan columnas {sorted(faltan)}")
        print(f"  {p.name}: {len(df):,} filas")
        partes.append(df)
    return pd.concat(partes, ignore_index=True)


def _sin_tildes(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def preparar(a: pd.DataFrame) -> pd.DataFrame:
    n0 = len(a)
    a = a.drop_duplicates("_id").copy()
    print(f"  duplicados por _id eliminados: {n0 - len(a):,}")
    # Formatos vistos: "2026-01-13 10:36:15.329 UTC" y "2026-09-02 00:05:25.775000" (ambos UTC).
    txt = a["created_at"].astype(str).str.replace("T", " ", regex=False).str.replace(" UTC", "", regex=False).str[:19]
    a["f"] = pd.to_datetime(txt, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    malas = int(a["f"].isna().sum())
    if malas:
        print(f"  aviso: {malas:,} filas sin created_at válido se descartan")
    a = a[a["f"].notna()].copy()
    a["Anio"], a["Mes"] = a["f"].dt.year, a["f"].dt.month
    a["Trimestre"] = "Q" + ((a["Mes"] - 1) // 3 + 1).astype(str)
    a["Semestre"] = "S" + ((a["Mes"] - 1) // 6 + 1).astype(str)
    a["Programa"] = a["Alliance"].map(SIGLA).fillna(a["Alliance"])
    a["seg"] = pd.to_numeric(a["time_view"], errors="coerce").fillna(0)
    a["Rol"] = a["roles_string"].fillna("Sin rol")
    a["Grado"] = a["Grado"].fillna("No especificado")
    reg = a["regional_name"].fillna("").astype(str).str.strip().str.upper().map(_sin_tildes)
    a["region_norm"] = reg.replace({"": "Sin ubicación", "USUARIO SIN CENTRO": "Sin ubicación", "BAORUCO": "BAHORUCO"})
    return a


def agg(a: pd.DataFrame, por: list[str]) -> pd.DataFrame:
    g = a.groupby(por, dropna=False).agg(usuarios_activos=("user", "nunique"), horas_totales=("seg", "sum"),
                                        registros=("_id", "size")).reset_index()
    g["horas_totales"] = (g["horas_totales"] / 3600).round(1)
    return g


def salidas(a: pd.DataFrame) -> dict[str, pd.DataFrame]:
    dims = ["Rol", "Grado", "region_norm"]
    out = {}
    for grano, per in (("mensual", ["Anio", "Mes"]), ("trimestral", ["Anio", "Trimestre"]),
                       ("semestral", ["Anio", "Semestre"]), ("anual", ["Anio"])):
        out[f"totales_{grano}"] = agg(a, per + ["Programa"])
        out[f"detalle_{grano}"] = agg(a, per + ["Programa"] + dims)
    m = ["Anio", "Mes", "Alliance"]
    out["mensual_alianza"] = agg(a, m)
    out["mensual_alianza_rol"] = agg(a, m + ["roles_string"])
    out["mensual_alianza_grado"] = agg(a, m + ["Grado"])
    out["mensual_alianza_region"] = agg(a, m + ["region_norm"])
    out["mensual_alianza_app"] = agg(a, m + ["app"])
    return out


def fusionar(viejo: pd.DataFrame, nuevo: pd.DataFrame, anios: set[int]) -> pd.DataFrame:
    if viejo.empty:
        return nuevo
    nuevo = nuevo[viejo.columns]
    claves = [c for c in viejo.columns if c not in MET]
    r = pd.concat([viejo[~viejo["Anio"].isin(anios)], nuevo], ignore_index=True)
    orden = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "S1": 1, "S2": 2}
    return r.sort_values(claves, key=lambda s: s.map(orden).fillna(s) if s.name in ("Trimestre", "Semestre") else s,
                         na_position="first").reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crudo", default=str(ROOT / "data" / "iq" / "usage_hours" / "crudo"))
    ap.add_argument("--out", default=str(ROOT / "data" / "iq" / "usage_hours"))
    args = ap.parse_args()
    crudo, out = Path(args.crudo), Path(args.out)

    print("Leyendo exportes...")
    a = preparar(leer(crudo))
    anios = set(int(x) for x in a["Anio"].unique())
    for y in sorted(anios):
        ini = a.loc[a["Anio"] == y, "f"].min()
        if ini > pd.Timestamp(year=y, month=1, day=3):
            if (a["Anio"] == y).sum() < 50:  # bordes de un exporte (p. ej. 31-dic del año anterior)
                print(f"  aviso: {int((a['Anio'] == y).sum())} filas sueltas de {y} se ignoran (año no exportado)")
                a = a[a["Anio"] != y]
                continue
            sys.exit(f"El exporte de {y} empieza el {ini:%d/%m/%Y}: para recalcular {y} debe venir desde el 1 de enero.")
    anios = set(int(x) for x in a["Anio"].unique())
    print(f"Años que se recalculan: {sorted(anios)} · hasta {a['f'].max():%d/%m/%Y}")

    for nombre, df in salidas(a).items():
        p = out / f"{nombre}.csv"
        viejo = pd.read_csv(p) if p.exists() else pd.DataFrame()
        r = fusionar(viejo, df, anios)
        r.to_csv(p, index=False, encoding="utf-8")
        print(f"  {p.name}: {len(r):,} filas")

    # Cobertura: se reemplazan las ventanas de los años recalculados por una sola ventana con los exportes nuevos.
    pv = out / "cobertura_ventanas.csv"
    v = pd.read_csv(pv) if pv.exists() else pd.DataFrame(columns=["desde", "hasta", "alianzas_cubiertas", "plataformas_cubiertas"])
    v = v[~pd.to_datetime(v["desde"]).dt.year.isin(anios)]
    nuevas = pd.DataFrame([{"desde": f"{y}-01-01", "hasta": f"{a.loc[a['Anio'] == y, 'f'].max():%Y-%m-%d}",
                            "alianzas_cubiertas": "Todas las alianzas", "plataformas_cubiertas": "lms + app movil"}
                           for y in sorted(anios)])
    pd.concat([v, nuevas], ignore_index=True).to_csv(pv, index=False, encoding="utf-8")
    print("Listo. Haz commit SOLO de los CSV de data/iq/usage_hours/ (nunca de crudo/).")


if __name__ == "__main__":
    main()
