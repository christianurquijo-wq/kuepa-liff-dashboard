"""
Métricas del análisis de ejecuciones (pandas puro, sin Streamlit -> testeable).

Definiciones:
  - origen agrupado: "Botón panel" (origen=boton), "Programada" (cron / trigger
    de n8n), "Manual / otra" (GitHub UI, local, ejecución manual en n8n).
  - Éxito = estado EXITOSO. TIMEOUT cuenta como fallo.
  - Racha de fallos = ejecuciones consecutivas no exitosas desde la más reciente.
  - Periodicidad real = mediana de horas entre inicios consecutivos.
  - Atrasada = frecuencia esperada > 0 y la última ejecución es más vieja que
    1,5 x la frecuencia esperada (margen para variaciones del cron de GitHub).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ORIGEN_GRUPO = {
    "boton": "Botón panel",
    "cron": "Programada",
    "trigger": "Programada",
    "n8n_programado": "Programada",
}
ORDEN_ORIGEN = ["Botón panel", "Programada", "Manual / otra"]

# Nombres de respaldo para flujos de n8n que aún no tienen fila en el CATALOGO (la bitácora
# de n8n solo trae el ID del flujo). El CATALOGO siempre tiene prioridad: lo correcto es
# darles su fila allí (plataforma=n8n, script=<ID>). IDs tomados de los flujos exportados (oct-2026).
NOMBRES_N8N = {
    "ZQ1F20BxYKLORR13": "Suba · Documentos de obligaciones",
    "7atG8gnX6spvbSl1": "Suba · Documentos de obligaciones (versión anterior)",
    "0i1vQyKEYCmmG1qf": "STC 3.0 · Certificación y finalización",
    "2HGHTB23sOGaUYD2": "Colsubsidio · Consultas generales",
    "mAzhyVdNbhyfXA4p": "ECO+ · Notas y asistencia (SIS)",
    "zlXHHNyxDzxaLL0F": "JAE · Asistencias (SIS)",
    "j24qc9DOSocfgFoE": "STC 3.0 · Entregables logs SDDE",
    "NMnUtMvRNl9ikgZ9": "STC 3.0 · Remisiones (correo empresarial)",
    "JujLCQ9Jxv1PiHVK": "STC 3.0 · Logs de formación",
    "lDoeo7RTTd4nOkEB": "STC 3.0 · Comunicaciones (plantilla HTML)",
    "cNuhAVEh5H4439v9": "STC 3.0 · Reportes y CRM",
    "o2vrXEIDnb1lsFR3": "JAE · Resultado de notas modulares",
    "VOa8YTfjoyipehU3": "STC 3.0 · VRD-FCS orientaciones",
}


def _nombre_respaldo(fila: pd.Series) -> str:
    """Nombre legible cuando la ejecución no cruza con el CATALOGO."""
    script = str(fila.get("script", ""))
    if fila.get("plataforma") == "n8n":
        return NOMBRES_N8N.get(script, f"Flujo n8n {script[:6]}… (sin ficha)")
    return script
ORDEN_ESTADO = ["EXITOSO", "FALLIDO", "TIMEOUT"]


def preparar(log: pd.DataFrame, catalogo: pd.DataFrame) -> pd.DataFrame:
    if log.empty:
        return log.assign(origen_grupo=[], nombre=[], proyecto=[], exito=[])
    df = log.copy()
    df["origen_grupo"] = df["origen"].map(ORIGEN_GRUPO).fillna("Manual / otra")
    df["exito"] = df["estado"].eq("EXITOSO")
    if not catalogo.empty:
        # Varias filas del CATALOGO pueden apuntar al mismo workflow (ej. 2 webhooks
        # de n8n en un flujo): se toma la primera para no duplicar ejecuciones.
        mapa = (catalogo.drop_duplicates("automatizacion_id")
                .set_index("automatizacion_id")[["nombre", "proyecto"]])
        df = df.join(mapa, on="automatizacion_id")
    else:
        df["nombre"], df["proyecto"] = np.nan, np.nan
    sin_nombre = df["nombre"].isna() | df["nombre"].astype(str).str.strip().eq("")
    df.loc[sin_nombre, "nombre"] = df[sin_nombre].apply(_nombre_respaldo, axis=1)
    df["proyecto"] = df["proyecto"].fillna("Sin catálogo").replace("", "Sin catálogo")
    df["dia"] = df["fecha_inicio"].dt.floor("D")
    df["hora"] = df["fecha_inicio"].dt.hour
    df["dia_semana"] = df["fecha_inicio"].dt.dayofweek
    return df


def kpis(df: pd.DataFrame) -> dict:
    total = len(df)
    exitosas = int(df["exito"].sum()) if total else 0
    ultimo = (df.sort_values("fecha_inicio").groupby("automatizacion_id").tail(1) if total else df)
    return {
        "total": total,
        "exito_pct": (exitosas / total * 100) if total else 0.0,
        "fallidas": total - exitosas,
        "dur_mediana": float(df["duracion_seg"].median()) if total else 0.0,
        "en_falla": int((~ultimo["exito"]).sum()) if total else 0,
        "por_boton": int(df["origen_grupo"].eq("Botón panel").sum()) if total else 0,
        "programadas": int(df["origen_grupo"].eq("Programada").sum()) if total else 0,
    }


def _racha(estados: pd.Series) -> int:
    n = 0
    for ok in reversed(estados.tolist()):
        if ok:
            break
        n += 1
    return n


def salud(df: pd.DataFrame, catalogo: pd.DataFrame, ahora: pd.Timestamp) -> pd.DataFrame:
    """Una fila por automatización del catálogo (+ las que aparecen en el log sin catálogo)."""
    filas = []
    grupos = {k: g.sort_values("fecha_inicio") for k, g in df.groupby("automatizacion_id")} if len(df) else {}
    base = catalogo[catalogo["activo"] & ~catalogo["script"].astype(str).str.startswith("lote:")] \
        if not catalogo.empty else pd.DataFrame(columns=["automatizacion_id"])
    ids = list(dict.fromkeys(list(base["automatizacion_id"]) + list(grupos)))
    cat = (catalogo.drop_duplicates("automatizacion_id").set_index("automatizacion_id")
           if not catalogo.empty else pd.DataFrame())
    for aid in ids:
        g = grupos.get(aid)
        info = cat.loc[aid] if aid in cat.index else None
        freq = float(info["frecuencia_horas"]) if info is not None else 0.0
        fila = {
            "automatizacion_id": aid,
            "nombre": info["nombre"] if info is not None else aid.split(":", 1)[-1],
            "proyecto": info["proyecto"] if info is not None else "Sin catálogo",
            "activo": bool(info["activo"]) if info is not None else True,
            "frecuencia_esperada_h": freq or None,
        }
        if g is None or g.empty:
            fila.update({"ejecuciones": 0, "ultimo_estado": "SIN DATOS", "atrasada": freq > 0})
        else:
            ult = g.iloc[-1]
            horas_desde = (ahora - ult["fecha_inicio"]).total_seconds() / 3600
            difs = g["fecha_inicio"].diff().dt.total_seconds().dropna() / 3600
            fila.update({
                "ejecuciones": len(g),
                "exito_pct": g["exito"].mean() * 100,
                "ultima_ejecucion": ult["fecha_inicio"],
                "ultimo_estado": ult["estado"],
                "horas_desde_ultima": horas_desde,
                "racha_fallos": _racha(g["exito"]),
                "periodicidad_real_h": float(difs.median()) if len(difs) else None,
                "dur_p50_seg": float(g["duracion_seg"].quantile(0.5)),
                "dur_p95_seg": float(g["duracion_seg"].quantile(0.95)),
                "atrasada": bool(freq > 0 and horas_desde > 1.5 * freq),
            })
        filas.append(fila)
    out = pd.DataFrame(filas)
    if out.empty:
        return out
    # Primero lo que requiere atención
    for col in ("racha_fallos", "exito_pct", "ultima_ejecucion", "horas_desde_ultima",
                "periodicidad_real_h", "dur_p50_seg", "dur_p95_seg"):
        if col not in out:
            out[col] = np.nan
    out["_prio"] = (out["racha_fallos"].fillna(0) > 0).astype(int) * 2 + out["atrasada"].fillna(False).astype(int)
    return out.sort_values(["_prio", "proyecto", "nombre"], ascending=[False, True, True]).drop(columns="_prio")


def por_dia_estado(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby(["dia", "estado"]).size().rename("ejecuciones").reset_index()


def por_dia_origen(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby(["dia", "origen_grupo"]).size().rename("ejecuciones").reset_index()


def duraciones(df: pd.DataFrame, top: int = 15) -> pd.DataFrame:
    d = (df.groupby("nombre")["duracion_seg"]
         .agg(p50=lambda s: s.quantile(0.5), p95=lambda s: s.quantile(0.95), n="count")
         .reset_index())
    return d.sort_values("p95", ascending=False).head(top)


def mapa_calor(df: pd.DataFrame) -> pd.DataFrame:
    m = df.groupby(["dia_semana", "hora"]).size().unstack(fill_value=0)
    return m.reindex(index=range(7), columns=range(24), fill_value=0)


def ultimo_lote(df: pd.DataFrame, lote: str) -> dict | None:
    """Estado de la última corrida de un lote (todas sus filas comparten run_url)."""
    sub = df[df["lote"].eq(lote)]
    if sub.empty:
        return None
    run = sub.sort_values("fecha_inicio").iloc[-1]["run_url"]
    corrida = sub[sub["run_url"].eq(run)] if run else sub.tail(1)
    return {
        "inicio": corrida["fecha_inicio"].min(),
        "fin": corrida["fecha_fin"].max(),
        "scripts": len(corrida),
        "fallidos": int((~corrida["exito"]).sum()),
        "run_url": run,
    }
