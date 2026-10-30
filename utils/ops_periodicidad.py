"""
Periodicidad de cada automatización (oct-2026): etiqueta de color junto al nombre, filtro del Panel
y alerta de desfase.

Fuente: columnas del CATALOGO que llena _reorg/ops_periodicidad.py leyendo los cron de GitHub
Actions y los Schedule Trigger de n8n:
  periodicidad_tipo     HORAS | DIARIA | SEMANAL | MENSUAL | MANUAL | EVENTO | LOTE
  periodicidad_detalle  ej. «11:00 p. m.», «lun a vie · 6:00 a. m.», «Lote nocturno · 11:00 p. m.»
  periodicidad_horas    máximo de horas entre dos ejecuciones programadas (0 = no corre sola)
  periodicidad_fuente   AUTO (script) | MANUAL (corregida a mano; el script no la toca)
Si una fila aún no tiene esos datos, se deduce de frecuencia_horas / frecuencia (lo de antes).

normalizar() también alinea frecuencia_horas con periodicidad_horas, así la semáforo del Manual y
la columna «Atrasada» del Análisis usan el mismo horario que muestra la etiqueta.
"""
from __future__ import annotations

import html

import pandas as pd

# tipo -> (nombre corto, color, ícono)
TIPOS: dict[str, tuple[str, str, str]] = {
    "HORAS": ("Varias veces al día", "#26C6DA", "⏱"),
    "DIARIA": ("Diaria", "#29B6F6", "📅"),
    "SEMANAL": ("Semanal", "#AB7DF6", "🗓"),
    "MENSUAL": ("Mensual", "#F5B942", "🗓"),
    "LOTE": ("En lote", "#FD8A5E", "📦"),
    "EVENTO": ("Por evento", "#EC6FA0", "⚡"),
    "MANUAL": ("Manual", "#9E9E9E", "👆"),
}
ORDEN = list(TIPOS)
PROGRAMADAS = {"HORAS", "DIARIA", "SEMANAL", "MENSUAL", "LOTE"}
COLUMNAS = ["periodicidad_tipo", "periodicidad_detalle", "periodicidad_horas", "periodicidad_fuente"]
MARGEN = 1.5  # misma tolerancia que ya usaba el panel (el cron de GitHub se retrasa a veces)


def _deducir(fila: pd.Series) -> tuple[str, str]:
    """Para filas sin periodicidad del script: lo que dice frecuencia_horas / frecuencia."""
    f = float(fila.get("frecuencia_horas") or 0)
    texto = str(fila.get("frecuencia", "") or "").strip()
    if f <= 0:
        return "MANUAL", "" if texto.lower() in ("", "manual", "a demanda") else texto
    if f < 24:
        return "HORAS", texto or f"Cada {f:g} h"
    if f <= 24:
        return "DIARIA", texto
    if f <= 24 * 7:
        return "SEMANAL", texto
    return "MENSUAL", texto


def normalizar(catalogo: pd.DataFrame) -> pd.DataFrame:
    df = catalogo.copy()
    if df.empty:
        return df
    for c in COLUMNAS:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].fillna("").astype(str).str.strip()
    df["periodicidad_tipo"] = df["periodicidad_tipo"].str.upper()
    df["periodicidad_fuente"] = df["periodicidad_fuente"].str.upper()
    horas = pd.to_numeric(df["periodicidad_horas"].str.replace(",", "."), errors="coerce")
    tiene = df["periodicidad_tipo"].isin(TIPOS.keys())
    # Filas con periodicidad leída/corregida: su horario manda también en frecuencia_horas.
    if "frecuencia_horas" in df:
        df.loc[tiene, "frecuencia_horas"] = horas[tiene].fillna(0)
    df["periodicidad_horas"] = horas.fillna(pd.to_numeric(df.get("frecuencia_horas", 0), errors="coerce")).fillna(0)
    for i in df.index[~tiene]:
        df.at[i, "periodicidad_tipo"], df.at[i, "periodicidad_detalle"] = _deducir(df.loc[i])
        df.at[i, "periodicidad_fuente"] = "SIN_LEER"
    df["periodicidad"] = df.apply(etiqueta, axis=1)
    return df


def etiqueta(fila) -> str:
    """Texto de la etiqueta: «Diaria · 11:00 p. m.», «Cada 4 h», «Lote nocturno · 11:00 p. m.», «Manual»."""
    tipo = str(fila.get("periodicidad_tipo", "") or "MANUAL")
    det = str(fila.get("periodicidad_detalle", "") or "").strip()
    nombre = TIPOS.get(tipo, TIPOS["MANUAL"])[0]
    if tipo in ("HORAS", "LOTE") and det:
        return det
    if fila.get("periodicidad_fuente") == "SIN_LEER" and det:
        return det  # texto libre de la columna «frecuencia» (aún sin leer los horarios reales)
    if tipo == "MANUAL" and det.lower() in ("botón del panel", "boton del panel"):
        return nombre
    return f"{nombre} · {det}" if det else nombre


def chip(fila, alerta: str = "") -> str:
    tipo = str(fila.get("periodicidad_tipo", "") or "MANUAL")
    _, color, icono = TIPOS.get(tipo, TIPOS["MANUAL"])
    titulo = "Corregida a mano en el CATALOGO" if fila.get("periodicidad_fuente") == "MANUAL" else (
        "Leída de GitHub Actions / n8n" if fila.get("periodicidad_fuente") == "AUTO"
        else "Sin leer: falta correr _reorg/ops_periodicidad.py")
    html_chip = (f"<span title='{html.escape(titulo)}' style='display:inline-block;background:{color}22;"
                 f"color:{color};border:1px solid {color}66;padding:1px 9px;border-radius:10px;"
                 f"font-size:0.74rem;font-weight:600;white-space:nowrap;vertical-align:middle'>"
                 f"{icono} {html.escape(etiqueta(fila))}</span>")
    if alerta:
        html_chip += (f" <span title='{html.escape(alerta)}' style='display:inline-block;background:#E74C3C22;"
                      f"color:#FF7B6E;border:1px solid #E74C3C66;padding:1px 9px;border-radius:10px;"
                      f"font-size:0.74rem;font-weight:600;white-space:nowrap;vertical-align:middle'>"
                      f"⚠ {html.escape(_corto(alerta))}</span>")
    return html_chip


def _corto(alerta: str) -> str:
    return alerta.split(":", 1)[0]


def _h(horas: float) -> str:
    if horas < 48:
        return f"{horas:.0f} h"
    return f"{horas / 24:.0f} días"


def _ejecuciones(log: pd.DataFrame, fila) -> pd.DataFrame:
    if log is None or log.empty:
        return pd.DataFrame()
    script = str(fila.get("script", ""))
    if script.startswith("lote:") and "lote" in log:
        return log[log["lote"].astype(str).eq(script.split(":", 1)[1])]
    return log[log["automatizacion_id"].eq(fila.get("automatizacion_id"))]


def desfase(fila, log: pd.DataFrame, ahora: pd.Timestamp) -> str:
    """Texto de alerta si la periodicidad declarada no coincide con lo que pasa; "" si todo cuadra.
      - programada y sin correr hace más de 1,5× su intervalo -> «Atrasada: …»
      - marcada Manual/Evento pero con ejecuciones programadas recientes -> «Desactualizada: …»"""
    tipo = str(fila.get("periodicidad_tipo", ""))
    horas = float(fila.get("periodicidad_horas") or 0)
    sub = _ejecuciones(log, fila)
    if tipo in PROGRAMADAS and horas > 0:
        if sub.empty:
            return ""  # sin historial no se acusa (la tarjeta ya dice «SIN DATOS»)
        desde = (ahora - sub["fecha_inicio"].max()).total_seconds() / 3600
        if desde > MARGEN * horas:
            return (f"Atrasada: debía correr al menos cada {_h(horas)} y la última ejecución fue hace "
                    f"{_h(desde)}. Revisa que el cron de GitHub o el flujo de n8n sigan activos.")
        return ""
    if tipo in ("MANUAL", "EVENTO") and not sub.empty and "origen_grupo" in sub:
        recientes = sub[(sub["fecha_inicio"] >= ahora - pd.Timedelta(days=14))
                        & sub["origen_grupo"].eq("Programada")]
        if len(recientes) >= 2:
            return (f"Desactualizada: figura como «{TIPOS[tipo][0]}» pero corrió programada "
                    f"{len(recientes)} veces en 14 días. Corre _reorg/ops_periodicidad.py --aplicar.")
    return ""


def opciones_filtro(df: pd.DataFrame) -> list[str]:
    presentes = set(df["periodicidad_tipo"]) if "periodicidad_tipo" in df else set()
    return [TIPOS[t][0] for t in ORDEN if t in presentes]


def tipos_de(nombres: list[str]) -> set[str]:
    return {t for t, (n, _, _) in TIPOS.items() if n in nombres}
