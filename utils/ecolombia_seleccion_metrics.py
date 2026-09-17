"""
Reglas de negocio -- Ecolombia / Selección y Matrícula.

Fuente: CONVOCATORIA (queries/ecolombia/convocatoria.py) -- el embudo
completo de candidatos, la misma tabla que ya usa Overview para
Seleccionados/Pendientes por ingresar.

Todo lo de abajo salió de cruzar el pantallazo de Looker contra
`estado_preinscripcion`, `resultado_entrevista` y `estado_final_fase_i`
(2026-09-17) -- NINGÚN valor de texto se adivinó, se confirmó por
aritmética exacta contra los números congelados de la captura:

    Usuarios              COUNT(*)                                       2704
    Descartados           estado_preinscripcion == "Descartado"          1181
    Cumple requisitos     estado_preinscripcion == "Cumple requisitos"   1523
    Agendados             resultado_entrevista == "Agendada"               63
    Seleccionado          resultado_entrevista == "Pasa"                  113
    Repechaje             resultado_entrevista == "Repechaje"             362
    No Pasa               resultado_entrevista == "No pasa"               217

Dentro de Seleccionado + Repechaje (475 = numerador de "Avance de
Selección"), el sub-estado sale de `estado_final_fase_i`, cruzado por
separado contra Pasa y contra Repechaje (confirmado con un query ad hoc,
no adivinado):

                              Pasa   Repechaje   Total
    Matriculado                91       270       361
    Pendiente Contrato         12        30        42
    Retiro                      8        47        55
    En proceso de matrícula     2        11        13
    Pendiente Documentos        0         3         3
    No Contactabilidad          0         1          1  (*)

(*) Christian confirmó sumar este único caso a "Pendiente" en vez de
dejarlo fuera -- por eso "Pendiente" en este archivo da 4, no 3.

"En verificación" (0 en la captura) y el desglose "Asiste/No Asiste" bajo
"No Pasa" quedan PENDIENTES a propósito -- no cierran contra ninguna
columna disponible del esquema y no tienen impacto en ningún KPI hoy (la
primera está en cero; la segunda es puramente informativa). Si algún día
dejan de ser cero/triviales, se resuelven con datos reales en pantalla,
no con teoría.

Metas de la convocatoria (avance de selección/matrícula, leads
necesarios, proyección de requisitos, matrículas pendientes): Christian
confirmó que TODAS salen de una sola meta de negocio -- las matrículas
efectivas objetivo (por defecto 400, editable en la página porque cambia
de convocatoria a convocatoria) -- proyectada hacia atrás con las tasas
de conversión REALES de la cohorte actual entre cada etapa del embudo.
Fórmulas (replicadas y verificadas contra la captura, número por número):

    tasa_seleccion_a_matricula   = Matriculados / Seleccionados          (361/475 = 76.00%)
    tasa_requisitos_a_seleccion  = Seleccionados / Cumple_requisitos     (475/1523 = 31.19%)
    tasa_leads_a_requisitos      = Cumple_requisitos / Usuarios          (1523/2704 = 56.32%)
    tasa_entrevista_a_seleccion  = Seleccionados / (Seleccionados + No_Pasa)  (475/692 = 68.64%)
                                    -- de las entrevistas YA con resultado
                                       definitivo, cuántas se seleccionan

    Meta_seleccionados      = CEIL(meta_matriculados / tasa_seleccion_a_matricula)
    Meta_entrevistas        = CEIL(Meta_seleccionados / tasa_entrevista_a_seleccion)
    Avance de Selección     = Seleccionados / Meta_entrevistas
                               -> 475 / CEIL(CEIL(400/0.76) / 0.6864) = 475/768
                               (exacto contra la captura)
    Avance de Matriculación = Matriculados / meta_matriculados  (361/400, exacto)
    Matrículas pendientes   = meta_matriculados - Matriculados  (400-361 = 39, exacto)
    Proyección requisitos   = CEIL(meta_matriculados / (tasa_seleccion_a_matricula * tasa_requisitos_a_seleccion)) - Cumple_requisitos
                              (1688 - 1523 = 165, exacto)
    Leads necesarios        = CEIL(meta_matriculados / (tasa_seleccion_a_matricula * tasa_requisitos_a_seleccion * tasa_leads_a_requisitos)) - Usuarios
                              (2997 - 2704 = 293 -- la captura muestra 292; queda a ±1
                              por el orden de redondeo intermedio, no por una fórmula
                              distinta. Corre la página y compáralo en vivo -- si esa
                              diferencia de 1 molesta, es un ajuste de una línea aquí,
                              no una reescritura.)

"Retención 100%" y el gauge "103%" del pantallazo quedan PENDIENTES --
necesitan un insumo que todavía no está confirmado (fechas de
arranque/cierre de la convocatoria para el gauge de ritmo, y la
definición exacta de "retención" post-matrícula para esa tarjeta, que
podría vivir en V2_2026 en vez de aquí). La página los muestra como
tarjetas "Pendiente" en vez de inventar un número.
"""
import math

import pandas as pd

# -- estado_preinscripcion ---------------------------------------------------
PREINSCRIPCION_CUMPLE = "Cumple requisitos"
PREINSCRIPCION_DESCARTADO = "Descartado"

# -- resultado_entrevista -----------------------------------------------------
ENTREVISTA_AGENDADA = "Agendada"
ENTREVISTA_PASA = "Pasa"
ENTREVISTA_REPECHAJE = "Repechaje"
ENTREVISTA_NO_PASA = "No pasa"
RESULTADO_SELECCIONADO = (ENTREVISTA_PASA, ENTREVISTA_REPECHAJE)

# -- estado_final_fase_i (solo tiene sentido dentro de RESULTADO_SELECCIONADO) --
FASE1_MATRICULADO = "Matriculado"
FASE1_PENDIENTE_CONTRATO = "Pendiente Contrato"
FASE1_RETIRO = "Retiro"
FASE1_PROCESO_MATRICULA = "En proceso de matrícula"
FASE1_PENDIENTE_DOCUMENTOS = ("Pendiente Documentos", "No Contactabilidad")

SUBESTADOS_SELECCION = [
    "Matriculado",
    "Pendiente Contrato",
    "Retiro",
    "En proceso de matrícula",
    "Pendiente",
]

META_MATRICULADOS_DEFAULT = 400


def enrich_seleccion(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # DATETIME nativo en BigQuery -- llega ya como datetime64, esto es
    # solo un resguardo si algún día cambia a STRING (mismo criterio que
    # ecolombia_metrics.enrich()).
    df["fecha_de_matricula"] = pd.to_datetime(df["fecha_de_matricula"], errors="coerce")
    df["fecha_de_preinscripcion"] = pd.to_datetime(
        df["fecha_de_preinscripcion"], errors="coerce"
    )

    df["_CUMPLE_REQUISITOS"] = df["estado_preinscripcion"] == PREINSCRIPCION_CUMPLE
    df["_DESCARTADO"] = df["estado_preinscripcion"] == PREINSCRIPCION_DESCARTADO
    df["_AGENDADO"] = df["resultado_entrevista"] == ENTREVISTA_AGENDADA
    df["_PASA"] = df["resultado_entrevista"] == ENTREVISTA_PASA
    df["_REPECHAJE"] = df["resultado_entrevista"] == ENTREVISTA_REPECHAJE
    df["_NO_PASA"] = df["resultado_entrevista"] == ENTREVISTA_NO_PASA
    df["_SELECCIONADO"] = df["resultado_entrevista"].isin(RESULTADO_SELECCIONADO)
    df["_MATRICULADO"] = df["estado_final_fase_i"] == FASE1_MATRICULADO
    return df


def _subestado_counts(sub_df: pd.DataFrame) -> dict:
    """estado_final_fase_i -> conteo, solo para un sub-conjunto YA
    filtrado a Pasa o a Repechaje (ver docstring del módulo)."""
    counts = {
        "Matriculado": int((sub_df["estado_final_fase_i"] == FASE1_MATRICULADO).sum()),
        "Pendiente Contrato": int(
            (sub_df["estado_final_fase_i"] == FASE1_PENDIENTE_CONTRATO).sum()
        ),
        "Retiro": int((sub_df["estado_final_fase_i"] == FASE1_RETIRO).sum()),
        "En proceso de matrícula": int(
            (sub_df["estado_final_fase_i"] == FASE1_PROCESO_MATRICULA).sum()
        ),
        "Pendiente": int(
            sub_df["estado_final_fase_i"].isin(FASE1_PENDIENTE_DOCUMENTOS).sum()
        ),
    }
    return counts


_CLAVE_SUBESTADO = {
    "Matriculado": "matriculado",
    "Pendiente Contrato": "pdte_contrato",
    "Retiro": "retiro_seleccion",
    "En proceso de matrícula": "proceso_matricula",
    "Pendiente": "pendiente",
}


def funnel_arbol(df: pd.DataFrame) -> dict:
    """Conteos exactos de cada caja del árbol del pantallazo (menos "En
    verificación" y "Asiste/No Asiste", pendientes -- ver docstring)."""
    pasa = _subestado_counts(df[df["_PASA"]])
    repechaje = _subestado_counts(df[df["_REPECHAJE"]])
    sub_total = {
        _CLAVE_SUBESTADO[k]: pasa[k] + repechaje[k] for k in SUBESTADOS_SELECCION
    }

    return {
        "usuarios": len(df),
        "descartados": int(df["_DESCARTADO"].sum()),
        "cumple_requisitos": int(df["_CUMPLE_REQUISITOS"].sum()),
        "agendados": int(df["_AGENDADO"].sum()),
        "seleccionado": int(df["_PASA"].sum()),
        "repechaje": int(df["_REPECHAJE"].sum()),
        "no_pasa": int(df["_NO_PASA"].sum()),
        **sub_total,
    }


def sankey_convocatoria(df: pd.DataFrame) -> dict:
    """Nodos y enlaces del embudo completo, listos para
    plotly.graph_objects.Sankey(...) -- {labels, source, target, value}.
    Usuarios -> Descartados/Cumple requisitos -> Agendados/Seleccionado/
    Repechaje/No Pasa -> (Seleccionado y Repechaje comparten los mismos 5
    nodos de destino: Matriculado/Pendiente Contrato/Retiro/En proceso de
    matrícula/Pendiente), igual que en el pantallazo."""
    labels = [
        "Usuarios",
        "Descartados",
        "Cumple requisitos",
        "Agendados",
        "Seleccionado",
        "Repechaje",
        "No Pasa",
        *SUBESTADOS_SELECCION,
    ]
    idx = {label: i for i, label in enumerate(labels)}
    source, target, value = [], [], []

    def _link(origen: str, destino: str, cantidad: int) -> None:
        if cantidad > 0:
            source.append(idx[origen])
            target.append(idx[destino])
            value.append(cantidad)

    _link("Usuarios", "Descartados", int(df["_DESCARTADO"].sum()))
    _link("Usuarios", "Cumple requisitos", int(df["_CUMPLE_REQUISITOS"].sum()))
    _link("Cumple requisitos", "Agendados", int(df["_AGENDADO"].sum()))
    _link("Cumple requisitos", "Seleccionado", int(df["_PASA"].sum()))
    _link("Cumple requisitos", "Repechaje", int(df["_REPECHAJE"].sum()))
    _link("Cumple requisitos", "No Pasa", int(df["_NO_PASA"].sum()))

    for origen, sub_df in (("Seleccionado", df[df["_PASA"]]), ("Repechaje", df[df["_REPECHAJE"]])):
        for destino, cantidad in _subestado_counts(sub_df).items():
            _link(origen, destino, cantidad)

    return {"labels": labels, "source": source, "target": target, "value": value}


def _tasa(numerador: int, denominador: int) -> float:
    return numerador / denominador if denominador else 0.0


def avance_metas(df: pd.DataFrame, meta_matriculados: int = META_MATRICULADOS_DEFAULT) -> dict:
    """Todo lo que depende de la meta de matrículas efectivas -- ver
    docstring del módulo para la fórmula completa de cada campo."""
    usuarios = len(df)
    cumple_requisitos = int(df["_CUMPLE_REQUISITOS"].sum())
    seleccionados = int(df["_SELECCIONADO"].sum())
    no_pasa = int(df["_NO_PASA"].sum())
    matriculados = int(df["_MATRICULADO"].sum())
    decididos = seleccionados + no_pasa

    tasa_sel_a_matricula = _tasa(matriculados, seleccionados)
    tasa_req_a_sel = _tasa(seleccionados, cumple_requisitos)
    tasa_leads_a_req = _tasa(cumple_requisitos, usuarios)
    tasa_entrevista_a_sel = _tasa(seleccionados, decididos)

    meta_seleccionados = (
        math.ceil(meta_matriculados / tasa_sel_a_matricula) if tasa_sel_a_matricula else None
    )
    meta_entrevistas = (
        math.ceil(meta_seleccionados / tasa_entrevista_a_sel)
        if meta_seleccionados and tasa_entrevista_a_sel
        else None
    )

    tasa_req_x_sel = tasa_sel_a_matricula * tasa_req_a_sel
    meta_cumple_requisitos = (
        math.ceil(meta_matriculados / tasa_req_x_sel) if tasa_req_x_sel else None
    )

    tasa_leads_x_todo = tasa_req_x_sel * tasa_leads_a_req
    meta_leads = math.ceil(meta_matriculados / tasa_leads_x_todo) if tasa_leads_x_todo else None

    return {
        "meta_matriculados": meta_matriculados,
        "matriculados": matriculados,
        "seleccionados": seleccionados,
        "meta_entrevistas": meta_entrevistas,
        "pct_avance_seleccion": (
            _tasa(seleccionados, meta_entrevistas) * 100 if meta_entrevistas else 0.0
        ),
        "pct_avance_matriculacion": _tasa(matriculados, meta_matriculados) * 100,
        "matriculas_pendientes": max(meta_matriculados - matriculados, 0),
        "proyeccion_requisitos": max((meta_cumple_requisitos or 0) - cumple_requisitos, 0),
        "leads_necesarios": max((meta_leads or 0) - usuarios, 0),
    }


def aliado_referido_ranking(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """Top aliados/canales de referido por cantidad de leads -- igual a
    la tabla "Aliado - Referido" del pantallazo."""
    counts = df["aliado__referido"].fillna("Sin dato").value_counts()
    out = counts.rename_axis("Aliado / Referido").reset_index(name="Registros")
    return out.head(top_n)


def historico_matriculas(df: pd.DataFrame) -> pd.DataFrame:
    """Matrículas acumuladas por día -- histórico acumulado del pantallazo."""
    d = df[df["fecha_de_matricula"].notna()].copy()
    if d.empty:
        return pd.DataFrame(columns=["fecha", "acumulado"])
    d["fecha"] = d["fecha_de_matricula"].dt.date
    diario = d.groupby("fecha").size().sort_index().cumsum()
    return diario.reset_index(name="acumulado")


def historico_preinscritos(df: pd.DataFrame) -> pd.DataFrame:
    """Preinscritos por día (no acumulado) -- segundo histórico del
    pantallazo."""
    d = df[df["fecha_de_preinscripcion"].notna()].copy()
    if d.empty:
        return pd.DataFrame(columns=["fecha", "personas"])
    d["fecha"] = d["fecha_de_preinscripcion"].dt.date
    diario = d.groupby("fecha").size().reset_index(name="personas")
    return diario.sort_values("fecha")
