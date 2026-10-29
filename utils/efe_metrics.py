"""
Reglas de negocio de la sección EFE General -- UN solo lugar para todas las páginas.

Definiciones aprobadas por Christian (oct-2026). En n8n cada pestaña tenía las suyas y
comparaba contra valores que no existen ("GRADUADO", "ACTIVO", "APROBADO" en mayúsculas),
por eso Impactados / Retención / Aprobación salían más bajos de lo real.

  Inscritos            todas las personas (documentos distintos) del proyecto
  Impactados           estado ∈ {Activo, Finalizado, Retiro, Aplazado, Expulsado}
                       (empezaron la formación; fuera: Matrícula no exitosa, En proceso de
                       matrícula, En espera de activación y vacíos)
  Activos/Finalizados  estado = Activo / Finalizado
  Deserción            (Retiro + Expulsado) ÷ Impactados
  Retención            (Activo + Finalizado + Aplazado) ÷ Impactados  (= 100% − Deserción)
  Aprobación           Aprobado ÷ (Aprobado + Reprobado)  -- "Pendiente publicar nota" no cuenta
  Nuevos               impactados según su Fecha_ingreso_formacion
  Satisfacción         promedio de Promedio_Satisfaccion (1–5), meta 4,5
  NPS                  % promotores (9–10) − % detractores (0–6), escala −100 a 100
  Contratados          Estado_contratacion ∈ {Contratado, Colocado}
  Tasa de colocación   Contratados ÷ participantes de empleabilidad
  % Nini               "Ni estudiar, ni trabajar" ÷ caracterizados
  % Bajos ingresos     "Hasta 1 SMMLV" ÷ caracterizados con dato de ingresos

Unidad: conteos de personas = documentos distintos; tasas (retención, deserción, aprobación)
= sobre inscripciones (persona x programa: en Colsubsidio una persona cursa varios programas).
Los datos de caracterización se usan TAL CUAL vienen (Christian: "se llenan así por una razón
puntual"), incluidos los valores fijos de Colsubsidio 2.0 y el "Pendiente" de Suba.
"""
from __future__ import annotations

import pandas as pd

IMPACTADO = {"Activo", "Finalizado", "Retiro", "Aplazado", "Expulsado"}
RETENIDO = {"Activo", "Finalizado", "Aplazado"}
DESERCION = {"Retiro", "Expulsado"}
CONTRATADO = {"Contratado", "Colocado"}
META_SATISFACCION = 4.5

# Grupos de la página de KPIs (igual que PROJECT_MAPPING del dashboard de n8n).
GRUPOS = {
    "Socios Talento Capital": "Further Education",
    "Socios Talento Capital 3.0 Básico": "Further Education",
    "Socios Talento Capital 3.0 Especializado": "Further Education",
    "Colsubsidio 2026": "Further Education",
    "Colsubsidio 2.0 2026": "Further Education",
    "Suba es Oportunidad": "Further Education",
    "Ecolombia 2.0": "Employability",
    "Jóvenes a la E": "Employability",
}

ORDEN_EDAD = ["Menos de 18", "18 a 24", "25 a 28", "29 a 35", "36 a 45", "46 a 55", "Más de 55"]


# --------------------------------------------------------------------------- utilidades
def limpio(serie: pd.Series) -> pd.Series:
    """Texto sin espacios; 'None', 'nan', '' -> NaN (NO toca 'Pendiente' ni 'Sin información')."""
    s = serie.astype("string").str.strip()
    return s.mask(s.str.lower().isin({"", "none", "nan", "null"}))


def _en(serie: pd.Series, valores: set) -> pd.Series:
    return limpio(serie).str.lower().isin({v.lower() for v in valores}).fillna(False).astype(bool)


def genero(serie: pd.Series) -> pd.Series:
    """Femenino / Masculino / Otro; '-', 'Sin informacion' y vacíos -> 'Sin dato' (solo para mostrar)."""
    s = limpio(serie)
    return s.where(~s.str.lower().isin({"-", "sin informacion", "sin información"}), None).fillna("Sin dato")


COLORES_GENERO = {"Femenino": "#FD531E", "Masculino": "#29B6F6", "Otro": "#F5B942", "Sin dato": "#8C8C8C"}


def pct(num: float, den: float) -> float | None:
    return round(100 * num / den, 1) if den else None


def fmt_pct(valor) -> str:
    return "–" if valor is None or pd.isna(valor) else f"{valor:,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_num(valor, dec: int = 0) -> str:
    if valor is None or pd.isna(valor):
        return "–"
    texto = f"{valor:,.{dec}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def fecha_flexible(serie: pd.Series) -> pd.Series:
    """Fechas en texto: 'AAAA-MM-DD' o 'DD/MM/AAAA' (formato colombiano). Lo demás -> NaT."""
    s = limpio(serie)
    iso = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    dmy = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")
    return iso.fillna(dmy)


# --------------------------------------------------------------------------- seguimiento
def prep_seguimiento(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ("Proyecto", "Programa", "Estado_academico", "Resultado_academico", "Ciudad", "Sexo"):
        if c in df:
            df[c] = limpio(df[c])
    df["Programa"] = df["Programa"].fillna("Sin programa")
    df["Estado_academico"] = df["Estado_academico"].fillna("Sin estado")
    df["impactado"] = _en(df["Estado_academico"], IMPACTADO)
    df["retenido"] = _en(df["Estado_academico"], RETENIDO)
    df["desertor"] = _en(df["Estado_academico"], DESERCION)
    df["aprobado"] = df["impactado"] & _en(df["Resultado_academico"], {"Aprobado"})
    df["reprobado"] = df["impactado"] & _en(df["Resultado_academico"], {"Reprobado"})
    df["fecha_ingreso"] = fecha_flexible(df.get("Fecha_ingreso_formacion", pd.Series(index=df.index, dtype="object")))
    df["fecha_fin"] = fecha_flexible(df.get("Fecha_fin_formacion", pd.Series(index=df.index, dtype="object")))
    return df


def kpis_seguimiento(df: pd.DataFrame) -> dict:
    """df ya pasado por prep_seguimiento (y filtrado)."""
    imp = df[df["impactado"]]
    insc_imp = len(imp)
    calificados = int(df["aprobado"].sum() + df["reprobado"].sum())
    estado = df["Estado_academico"].str.lower()
    return {
        "inscritos": df["Documento"].nunique(),
        "impactados": imp["Documento"].nunique(),
        "activos": df.loc[estado == "activo", "Documento"].nunique(),
        "finalizados": df.loc[estado == "finalizado", "Documento"].nunique(),
        "desertores": df.loc[df["desertor"], "Documento"].nunique(),
        "no_exitosa": df.loc[estado == "matrícula no exitosa", "Documento"].nunique(),
        "retencion": pct(df["retenido"].sum(), insc_imp),
        "desercion": pct(df["desertor"].sum(), insc_imp),
        "aprobacion": pct(df["aprobado"].sum(), calificados),
        "calificados": calificados,
        "pendiente_nota": int((df["impactado"] & _en(df["Resultado_academico"], {"Pendiente publicar nota"})).sum()),
    }


# --------------------------------------------------------------------------- satisfacción
DIMENSIONES_SAT = {
    "Docente": "Evaluacion_docente",
    "Contenidos": "Evaluacion_recursos_contenido",
    "Institución": "Evaluacion_institucion",
    "Plataforma": "Evaluacion_plataforma",
    "Psicosocial": "Evaluacion_psicosocial",
    "Autoevaluación": "Autoevaluacion",
}


def prep_satisfaccion(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Proyecto"] = limpio(df["Proyecto"])
    for c in list(DIMENSIONES_SAT.values()) + ["NPS", "Promedio_Satisfaccion"]:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["fecha"] = fecha_flexible(df["Fecha"]) if "Fecha" in df else pd.NaT
    emp = limpio(df.get("Evaluacion_empleabilidad", pd.Series(index=df.index, dtype="object")))
    df["recomienda_empleabilidad"] = emp.str.lower().str.replace("í", "i").map({"si": "Sí", "no": "No"})
    return df


def nps(serie: pd.Series) -> float | None:
    s = pd.to_numeric(serie, errors="coerce").dropna()
    if s.empty:
        return None
    return round(100 * ((s >= 9).mean() - (s <= 6).mean()), 1)


def nps_categoria(serie: pd.Series) -> pd.Series:
    s = pd.to_numeric(serie, errors="coerce")
    return pd.cut(s, bins=[-1, 6, 8, 10], labels=["Detractor (0–6)", "Pasivo (7–8)", "Promotor (9–10)"])


def kpis_satisfaccion(df: pd.DataFrame) -> dict:
    out = {"muestra": len(df), "nps": nps(df["NPS"]),
           "satisfaccion": round(df["Promedio_Satisfaccion"].mean(), 2) if df["Promedio_Satisfaccion"].notna().any() else None}
    for nombre, col in DIMENSIONES_SAT.items():
        out[nombre] = round(df[col].mean(), 2) if col in df and df[col].notna().any() else None
    return out


# --------------------------------------------------------------------------- caracterización
def prep_caracterizacion(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ("Proyecto", "Sexo", "Estrato", "Actividad_principal", "Ingresos", "Escolaridad",
              "Numero_hijos_Personas_cargo", "Ciudad_residencia"):
        if c in df:
            df[c] = limpio(df[c])
    df["Edad"] = pd.to_numeric(df["Edad"], errors="coerce")
    df["fecha"] = fecha_flexible(df["Fecha"]) if "Fecha" in df else pd.NaT
    # Una fila por persona y proyecto: la encuesta más reciente.
    df = df.sort_values("fecha").drop_duplicates(["Documento", "Proyecto"], keep="last")
    df["rango_edad"] = pd.cut(df["Edad"], bins=[0, 17, 24, 28, 35, 45, 55, 200], labels=ORDEN_EDAD)
    return df


def kpis_caracterizacion(df: pd.DataFrame) -> dict:
    act = df["Actividad_principal"].str.lower()
    sexo = df["Sexo"].str.lower()
    ingresos = df["Ingresos"].dropna()
    return {
        "caracterizados": df["Documento"].nunique(),
        "nini": pct((act == "ni estudiar, ni trabajar").sum(), act.notna().sum()),
        "mujeres": pct((sexo == "femenino").sum(), sexo.notna().sum()),
        "bajos_ingresos": pct((ingresos.str.lower() == "hasta 1 smmlv").sum(), len(ingresos)),
        "edad_promedio": round(df["Edad"].mean(), 1) if df["Edad"].notna().any() else None,
    }


# --------------------------------------------------------------------------- empleabilidad
def prep_empleabilidad(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ("Proyecto", "Ciudad", "Estado_contratacion", "Estado_academico", "Empresa"):
        if c in df:
            df[c] = limpio(df[c])
    df["Estado_contratacion"] = df["Estado_contratacion"].fillna("Sin estado")
    df["postulaciones"] = pd.to_numeric(df["Total_remisiones_postulaciones"], errors="coerce")
    df["contratado"] = _en(df["Estado_contratacion"], CONTRATADO)
    return df


def kpis_empleabilidad(df: pd.DataFrame) -> dict:
    est_acad = df["Estado_academico"].str.lower()
    participantes = df["Documento"].nunique()
    contratados = df.loc[df["contratado"], "Documento"].nunique()
    return {
        "participantes": participantes,
        "activos": df.loc[est_acad == "activo", "Documento"].nunique(),
        "desercion": pct(df.loc[_en(df["Estado_academico"], DESERCION), "Documento"].nunique(), participantes),
        "postulaciones": int(df["postulaciones"].sum(skipna=True)),
        "contratados": contratados,
        "colocacion": pct(contratados, participantes),
    }


# --------------------------------------------------------------------------- series de tiempo
PERIODOS = {"Día": "D", "Semana": "W-MON", "Mes": "MS", "Trimestre": "QS"}


def periodo(fechas: pd.Series, granularidad: str) -> pd.Series:
    """Fecha de inicio del periodo (semana = lunes)."""
    f = pd.to_datetime(fechas)
    if granularidad == "Día":
        return f.dt.normalize()
    if granularidad == "Semana":
        return (f - pd.to_timedelta(f.dt.weekday, unit="D")).dt.normalize()
    if granularidad == "Mes":
        return f.dt.to_period("M").dt.start_time
    return f.dt.to_period("Q").dt.start_time


def corte_por_periodo(serie: pd.DataFrame, granularidad: str, claves: list[str]) -> pd.DataFrame:
    """Para indicadores de STOCK (personas en un estado): de cada periodo se toma la ÚLTIMA foto
    disponible (corte). Así 'semana' muestra cómo cerró la semana, no la suma de 7 días."""
    s = serie.copy()
    s["Periodo"] = periodo(s["Fecha"], granularidad)
    ultima = s.groupby(["Periodo"] + claves)["Fecha"].transform("max")
    return s[s["Fecha"] == ultima].drop(columns="Fecha")


def tasas_serie(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Retención %"] = (100 * df["insc_retenidas"] / df["insc_impactadas"]).where(df["insc_impactadas"] > 0).round(1)
    df["Deserción %"] = (100 * df["insc_desertoras"] / df["insc_impactadas"]).where(df["insc_impactadas"] > 0).round(1)
    calif = df["insc_aprobadas"] + df["insc_reprobadas"]
    df["Aprobación %"] = (100 * df["insc_aprobadas"] / calif).where(calif > 0).round(1)
    return df


# --------------------------------------------------------------------------- KPIs históricos (Sheet)
def promedio_ponderado(valores: pd.Series, pesos: pd.Series) -> float | None:
    v = pd.to_numeric(valores, errors="coerce")
    w = pd.to_numeric(pesos, errors="coerce").fillna(0)
    ok = v.notna() & (w > 0)
    if not ok.any():
        return None
    return float((v[ok] * w[ok]).sum() / w[ok].sum())


def resumen_historico(h: pd.DataFrame) -> pd.DataFrame:
    """Por mes (sobre los proyectos filtrados): impactados sumados, nuevos = diferencia contra el
    mes anterior (o la columna 'nuevos' si viene llena), y tasas ponderadas por impactados.
    Misma lógica que la página 'KPIs históricos' de n8n."""
    filas = []
    meses = sorted(h["mes"].dropna().unique())
    previo = None
    for m in meses:
        x = h[h["mes"] == m]
        imp = pd.to_numeric(x["impactados"], errors="coerce").fillna(0).sum()
        nuevos_col = pd.to_numeric(x.get("nuevos"), errors="coerce").sum() if "nuevos" in x else 0
        # Primer mes del historial: todos sus impactados son nuevos (igual que en n8n).
        nuevos = nuevos_col if nuevos_col > 0 else max(0, imp - (previo or 0))
        filas.append({
            "mes": m, "impactados": imp, "nuevos": nuevos,
            "retencion": promedio_ponderado(x["retencion"], x["impactados"]),
            "aprobacion": promedio_ponderado(x["aprobacion"], x["impactados"]),
            "nps": promedio_ponderado(x["nps"], x["impactados"]),
            "satisfaccion": promedio_ponderado(x["satisfaccion"], x["impactados"]),
        })
        previo = imp
    out = pd.DataFrame(filas)
    for c in ("impactados", "nuevos", "retencion", "aprobacion", "nps", "satisfaccion"):
        if c in out:
            out[c] = pd.to_numeric(out[c], errors="coerce")  # None -> NaN (meses sin dato)
    return out
