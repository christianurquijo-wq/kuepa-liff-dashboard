"""
Reglas de negocio -- Ecolombia / Académico.

La población base (Activos/Deserciones/Retención) es EXACTAMENTE la misma
que en Overview -- por eso este archivo no redefine esas 3 columnas: la
página llama utils.ecolombia_metrics.enrich() + kpis_overview() y usa
directamente kpis["activos"], kpis["deserciones"], kpis["pct_desercion"],
kpis["pct_retencion"] de ahí. Aquí solo vive lo que es propio de Académico.

Esquema completo de ECOPLUS_V2_2026 confirmado (2026-09-17) -- resolvió
los 3 pendientes de la primera versión de este archivo:

    cantidad_de_modulos_cursados    (FLOAT) -- hermana de
    cantidad_de_modulos_aprobados   (FLOAT) -- la que ya usábamos para Finalizados
    nota_modulo_0 ... nota_modulo_7 (FLOAT) -- nota por módulo individual

Estado académico por estudiante (confirmado contra el pantallazo, 263 activos):

    Al día académicamente         cursados > 0 AND aprobados == cursados   240
    Con pendientes académicos     cursados > 0 AND aprobados <  cursados    17
    Pendientes por publicar nota  cursados == 0 (o NaN)                      6
    Calificables = Activos - Pendientes por publicar nota = 263 - 6 = 257
    Aprobados (KPI) = Al día académicamente = 240
    % Aprobados = Aprobados / Calificables = 240 / 257 = 93.4%

Es decir: NO hace falta adivinar un catálogo de valores de texto -- la
clasificación sale de comparar los 2 conteos que ya veníamos usando. Sin
eso confirmado, la primera versión de este archivo dejaba esto como
pendiente; ya no.

Sankey (módulos cursados -> módulos aprobados): cada estudiante activo es
un flujo de "N módulos cursados" a "M módulos aprobados" -- N y M son
justo cantidad_de_modulos_cursados/aprobados, sin necesitar una tabla
aparte en formato largo.

Tabla de % de aprobación por Módulo 0-7 (por programa/cohorte): usa
nota_modulo_0..7. Nota de aprobación confirmada con Christian: >= 3.0
sobre 5.0 (estándar colombiano), sobre los estudiantes que YA tienen nota
en ese módulo (NaN = módulo todavía no cursado, se excluye del
denominador de ESE módulo, no de los demás). Si el corte cambia algún
día, es la única constante de negocio de este archivo -- NOTA_APROBACION_MODULO
abajo.
"""
import pandas as pd

NOTA_APROBACION_MODULO = 3.0
MODULOS = list(range(8))  # nota_modulo_0 .. nota_modulo_7


def ciudad_counts_activos(df: pd.DataFrame) -> pd.DataFrame:
    """Estudiantes ACTIVOS por ciudad -- distinto de
    ecolombia_metrics.ciudad_counts(), que agrupa sobre Matriculados. Aquí
    la base es Activos (263), confirmado contra el pantallazo (Bogotá
    159 + Medellín 52 + Cartagena 52 = 263)."""
    d = df[df["_ACTIVO"]]
    out = d.groupby("ciudad").size().reset_index(name="estudiantes")
    return out.sort_values("estudiantes", ascending=False)


def enrich_academico(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega _ESTADO_ACAD (Al día académicamente / Con pendientes
    académicos / Pendientes por publicar nota) -- solo tiene sentido para
    estudiantes activos, pero se calcula para todo el df sin filtrar."""
    df = df.copy()
    cursados = df["cantidad_de_modulos_cursados"].fillna(0)
    aprobados = df["cantidad_de_modulos_aprobados"].fillna(0)

    def _clasificar(cur, apr) -> str:
        if cur <= 0:
            return "Pendientes por publicar nota"
        if apr >= cur:
            return "Al día académicamente"
        return "Con pendientes académicos"

    df["_ESTADO_ACAD"] = [
        _clasificar(c, a) for c, a in zip(cursados, aprobados)
    ]
    return df


def kpis_academico(df: pd.DataFrame) -> dict:
    """df ya debe venir de enrich_academico(). KPIs sobre Activos."""
    activos = df[df["_ACTIVO"]]
    total_activos = len(activos)
    al_dia = int((activos["_ESTADO_ACAD"] == "Al día académicamente").sum())
    con_pendientes = int((activos["_ESTADO_ACAD"] == "Con pendientes académicos").sum())
    pendientes_nota = int((activos["_ESTADO_ACAD"] == "Pendientes por publicar nota").sum())
    calificables = total_activos - pendientes_nota
    pct_aprobados = (al_dia / calificables * 100) if calificables else 0.0

    return {
        "activos": total_activos,
        "aprobados": al_dia,
        "con_pendientes": con_pendientes,
        "pendientes_nota": pendientes_nota,
        "calificables": calificables,
        "pct_aprobados": pct_aprobados,
    }


def estado_academico_por_programa(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por (programa, _ESTADO_ACAD) con el conteo -- insumo de la
    barra apilada. Fuerza las 3 categorías con 0 si faltan, para que la
    barra no pierda un color cuando un programa no tiene esa categoría."""
    ORDEN = ["Al día académicamente", "Con pendientes académicos", "Pendientes por publicar nota"]
    activos = df[df["_ACTIVO"]]
    filas = []
    for programa in sorted(activos["programa"].dropna().unique()):
        sub = activos[activos["programa"] == programa]
        for categoria in ORDEN:
            filas.append(
                {
                    "programa": programa,
                    "categoria": categoria,
                    "cantidad": int((sub["_ESTADO_ACAD"] == categoria).sum()),
                }
            )
    return pd.DataFrame(filas)


def sankey_modulos(df: pd.DataFrame) -> dict:
    """
    Nodos y enlaces para un Sankey "N módulos cursados -> M módulos
    aprobados" sobre estudiantes activos. Cada estudiante activo con
    cursados > 0 aporta 1 al flujo (cursados[i] -> aprobados[i]).

    Devuelve un dict listo para plotly.graph_objects.Sankey(...): {label,
    source, target, value, n_cursados}. Los nodos de cursados y de
    aprobados son DISTINTOS aunque compartan el mismo número (ej. "6
    cursados" no es el mismo nodo que "6 aprobados") -- así se ve el
    flujo, no un punto fijo. `n_cursados` es cuántos de los primeros
    `labels` son nodos de "cursados" (el resto son de "aprobados") --
    la página lo usa para pintar los 2 grupos de nodos con colores
    distintos.
    """
    activos = df[df["_ACTIVO"] & (df["cantidad_de_modulos_cursados"].fillna(0) > 0)]
    flujos = (
        activos.groupby(
            [
                activos["cantidad_de_modulos_cursados"].astype(int),
                activos["cantidad_de_modulos_aprobados"].fillna(0).astype(int),
            ]
        )
        .size()
        .reset_index(name="cantidad")
    )
    flujos.columns = ["cursados", "aprobados", "cantidad"]

    nodos_cursados = sorted(flujos["cursados"].unique())
    nodos_aprobados = sorted(flujos["aprobados"].unique())

    labels = [f"{n} Módulo{'s' if n != 1 else ''} cursado{'s' if n != 1 else ''}" for n in nodos_cursados]
    labels += [
        f"{n} Módulo{'s' if n != 1 else ''} aprobado{'s' if n != 1 else ''}"
        if n > 0
        else "Sin módulos aprobados"
        for n in nodos_aprobados
    ]
    idx_cursados = {n: i for i, n in enumerate(nodos_cursados)}
    idx_aprobados = {n: i + len(nodos_cursados) for i, n in enumerate(nodos_aprobados)}

    source = [idx_cursados[c] for c in flujos["cursados"]]
    target = [idx_aprobados[a] for a in flujos["aprobados"]]
    value = flujos["cantidad"].tolist()

    return {
        "labels": labels,
        "source": source,
        "target": target,
        "value": value,
        "n_cursados": len(nodos_cursados),
    }


def tabla_modulo_aprobacion(df: pd.DataFrame) -> pd.DataFrame:
    """
    % de estudiantes activos con nota >= NOTA_APROBACION_MODULO en cada
    módulo (Módulo 0..7), por programa/cohorte -- más una fila "Total".
    El denominador de cada módulo son solo los estudiantes que YA tienen
    nota ahí (nota_modulo_i no nulo) -- los que no han llegado a ese
    módulo no cuentan ni a favor ni en contra de ESE módulo.
    """
    activos = df[df["_ACTIVO"]].copy()

    def _pct_modulo(sub: pd.DataFrame, i: int) -> float:
        col = f"nota_modulo_{i}"
        calificados = sub[col].notna()
        total = int(calificados.sum())
        if total == 0:
            return float("nan")
        aprobados = int((sub.loc[calificados, col] >= NOTA_APROBACION_MODULO).sum())
        return aprobados / total * 100

    filas = []
    total_row = {"programa": "Total", "cohorte": ""}
    for i in MODULOS:
        total_row[f"Módulo {i}"] = _pct_modulo(activos, i)
    filas.append(total_row)

    for (programa, cohorte), sub in activos.groupby(["programa", "cohorte"]):
        fila = {"programa": programa, "cohorte": cohorte}
        for i in MODULOS:
            fila[f"Módulo {i}"] = _pct_modulo(sub, i)
        filas.append(fila)

    return pd.DataFrame(filas)
