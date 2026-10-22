"""
Lógica del Manual de automatizaciones (pandas puro, sin Streamlit -> testeable).

Fuente: el mismo CATALOGO del Sheet de operaciones, con 5 columnas de manual
(para_que_sirve, cuando_usarla, entrada, salida, si_falla) que se agregan y
llenan con scripts/ops_manual_catalogo.py y luego el equipo edita en el Sheet.
Si esas columnas aún no existen, el manual funciona igual y marca las fichas
como pendientes.

Semáforo por automatización (a partir de LOG_EJECUCIONES):
  REQUIERE  última ejecución fallida / timeout, o atrasada (> 1,5x su frecuencia)
  AL_DIA    última ejecución exitosa y dentro de su frecuencia
  MANUAL    solo se corre a mano (frecuencia 0) y no tiene fallos recientes
  SIN_DATOS programada pero nunca registrada
  INACTIVA  en el catálogo pero sin botón (activo = NO)
"""
from __future__ import annotations

import re

import pandas as pd

COLUMNAS_MANUAL = ["para_que_sirve", "cuando_usarla", "entrada", "salida", "si_falla"]

SEMAFORO = {
    "REQUIERE": ("🔴", "Requiere atención"),
    "SIN_DATOS": ("🟠", "Sin ejecuciones registradas"),
    "AL_DIA": ("🟢", "Al día"),
    "MANUAL": ("🔵", "Manual"),
    "INACTIVA": ("⚪", "Pendiente de habilitar"),
}
ORDEN_SEMAFORO = ["REQUIERE", "SIN_DATOS", "AL_DIA", "MANUAL", "INACTIVA"]


def normalizar(catalogo: pd.DataFrame) -> pd.DataFrame:
    """Garantiza las columnas del manual (vacías si el Sheet aún no las tiene)."""
    df = catalogo.copy()
    for col in COLUMNAS_MANUAL + ["descripcion", "frecuencia", "responsable"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["ficha_completa"] = df[["para_que_sirve", "cuando_usarla"]].ne("").all(axis=1)
    return df


def partes(texto: str) -> list[str]:
    return [p.strip() for p in re.split(r"[;\n]", str(texto or "")) if p.strip()]


def _ultimo(log: pd.DataFrame, item: pd.Series) -> dict | None:
    """Última ejecución (o última corrida del lote) de una automatización."""
    if log.empty:
        return None
    script = str(item["script"])
    if script.startswith("lote:"):
        sub = log[log["lote"].eq(script.split(":", 1)[1])] if "lote" in log else log.iloc[0:0]
        if sub.empty:
            return None
        run = sub.iloc[-1]["run_url"]
        corrida = sub[sub["run_url"].eq(run)] if run else sub.tail(1)
        fallidos = int((corrida["estado"] != "EXITOSO").sum())
        return {"fecha": corrida["fecha_inicio"].min(), "estado": "EXITOSO" if fallidos == 0 else "FALLIDO",
                "detalle": f"{len(corrida)} scripts · {fallidos} fallidos",
                "duracion_seg": (corrida["fecha_fin"].max() - corrida["fecha_inicio"].min()).total_seconds(),
                "error": "; ".join(corrida.loc[corrida["estado"] != "EXITOSO", "script"].astype(str)),
                "run_url": run}
    sub = log[log["automatizacion_id"].eq(item["automatizacion_id"])]
    if sub.empty:
        return None
    u = sub.iloc[-1]
    return {"fecha": u["fecha_inicio"], "estado": u["estado"], "detalle": str(u.get("origen", "")),
            "duracion_seg": u["duracion_seg"], "error": str(u.get("error", "") or ""),
            "run_url": str(u.get("run_url", "") or "")}


def estados(catalogo: pd.DataFrame, log: pd.DataFrame, ahora: pd.Timestamp) -> pd.DataFrame:
    """Agrega al catálogo: semaforo, motivo y datos de la última ejecución."""
    filas = []
    for _, item in catalogo.iterrows():
        ult = _ultimo(log, item)
        freq = float(item.get("frecuencia_horas") or 0)
        horas = (ahora - ult["fecha"]).total_seconds() / 3600 if ult else None
        if not item["activo"]:
            sem, motivo = "INACTIVA", "Está en el catálogo pero aún no tiene botón."
        elif ult and ult["estado"] != "EXITOSO":
            sem, motivo = "REQUIERE", f"La última ejecución terminó en {ult['estado']}."
        elif freq > 0 and ult is None:
            sem, motivo = "SIN_DATOS", "Debería correr sola pero no hay ejecuciones registradas."
        elif freq > 0 and horas is not None and horas > 1.5 * freq:
            sem, motivo = "REQUIERE", f"Atrasada: no corre hace {horas:.0f} h (esperado cada {freq:.0f} h)."
        elif freq > 0:
            sem, motivo = "AL_DIA", "Corrió bien dentro de su frecuencia."
        else:
            sem, motivo = "MANUAL", "Se ejecuta a mano cuando se necesita."
        filas.append({
            "semaforo": sem, "motivo": motivo,
            "ultima_fecha": ult["fecha"] if ult else pd.NaT,
            "ultimo_estado": ult["estado"] if ult else "",
            "ultimo_detalle": ult["detalle"] if ult else "",
            "ultima_duracion_seg": ult["duracion_seg"] if ult else None,
            "ultimo_error": ult["error"] if ult else "",
            "ultimo_run_url": ult["run_url"] if ult else "",
        })
    return pd.concat([catalogo.reset_index(drop=True), pd.DataFrame(filas)], axis=1)


def buscar(df: pd.DataFrame, texto: str) -> pd.DataFrame:
    """Búsqueda simple sin tildes ni mayúsculas en nombre, proyecto, script y textos del manual."""
    if not texto.strip():
        return df
    campos = ["nombre", "proyecto", "script", "descripcion"] + COLUMNAS_MANUAL
    blob = df[campos].astype(str).agg(" ".join, axis=1).map(_plano)
    terminos = _plano(texto).split()
    return df[blob.map(lambda b: all(t in b for t in terminos))]


def _plano(texto: str) -> str:
    tabla = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    return str(texto).translate(tabla).lower()


# ------------------------------------------------------------------ diagrama
_FORMAS = {  # prefijo -> (forma graphviz, color de relleno)
    "sheet": ("note", "#1E4D2B"),
    "bigquery": ("cylinder", "#16365C"),
    "drive": ("folder", "#4A3B12"),
    "correo": ("box", "#4A1F3B"),
    "firestore": ("cylinder", "#4A2B12"),
    "web": ("box3d", "#2F2F2F"),
    "dashboard": ("tab", "#3B1F4A"),
    "proceso": ("component", "#2F2F2F"),
}
_COLOR_SEM = {"REQUIERE": "#E74C3C", "SIN_DATOS": "#F5B942", "AL_DIA": "#2ECC71",
              "MANUAL": "#29B6F6", "INACTIVA": "#8C8C8C"}


def _nodo(texto: str) -> tuple[str, str, str]:
    """'BigQuery: EFE_2026.X' -> (id, etiqueta, atributos)."""
    tipo, _, resto = texto.partition(":")
    tipo_l = tipo.strip().lower()
    if tipo_l not in _FORMAS or not resto.strip():
        tipo_l, resto = "proceso", texto
    forma, color = _FORMAS[tipo_l]
    etiqueta = resto.strip().replace("›", "\n›")
    nid = "n_" + re.sub(r"\W+", "_", f"{tipo_l}_{resto.strip()}".lower())[:60]
    attrs = f'shape={forma}, style="filled", fillcolor="{color}", fontcolor="white", color="#666666"'
    return nid, f"{tipo.strip().capitalize() if tipo_l != 'proceso' else '⚙'}\n{etiqueta}", attrs


def diagrama_dot(df: pd.DataFrame) -> str:
    """DOT de Graphviz: fuentes -> automatización -> destinos, coloreado por semáforo."""
    lineas = ['digraph G {', 'rankdir=LR; bgcolor="transparent"; nodesep=0.25; ranksep=0.9;',
              'node [fontname="Helvetica", fontsize=10]; edge [color="#888888", arrowsize=0.7];']
    vistos: set[str] = set()
    for _, r in df.iterrows():
        aid = "a_" + re.sub(r"\W+", "_", str(r["id"]))
        color = _COLOR_SEM.get(r.get("semaforo", ""), "#8C8C8C")
        nombre = str(r["nombre"]).replace('"', "'")
        lineas.append(f'{aid} [label="{nombre}", shape=box, style="rounded,filled,bold", '
                      f'fillcolor="#1A1A1A", fontcolor="white", color="{color}", penwidth=2.5];')
        for lado in ("entrada", "salida"):
            for parte in partes(r.get(lado, "")):
                nid, etiqueta, attrs = _nodo(parte)
                if nid not in vistos:
                    vistos.add(nid)
                    etiqueta = etiqueta.replace('"', "'")
                    lineas.append(f'{nid} [label="{etiqueta}", {attrs}];')
                lineas.append(f"{nid} -> {aid};" if lado == "entrada" else f"{aid} -> {nid};")
    lineas.append("}")
    return "\n".join(lineas)


# ------------------------------------------------------------------ guía de errores
# (síntoma, dónde se ve, causa probable, qué hacer). Errores reales vistos en oct-2026.
GUIA_ERRORES: list[dict] = [
    {"sintoma": "«no tiene las siguientes columnas» / «tiene columnas que no son de BQ»",
     "donde": "Cargas Sheet → BigQuery (EFE, STC)",
     "causa": "Alguien cambió, agregó o borró un encabezado en la pestaña de origen. El script se detiene "
              "a propósito para no dañar la tabla.",
     "accion": "Si el cambio fue un error, restaura el encabezado en el Sheet y vuelve a ejecutar. Si las "
               "columnas nuevas son intencionales, pide a Datos que las agregue a la tabla de BigQuery."},
    {"sintoma": "Aparece una columna «________» o «__index_level_0__»",
     "donde": "Cargas Sheet → BigQuery",
     "causa": "Un encabezado quedó vacío o con solo espacios, o un índice interno se coló en la carga.",
     "accion": "Pon nombre a la columna en el Sheet. Si persiste, avisa a Datos (ya hay correcciones para "
               "los casos conocidos)."},
    {"sintoma": "KeyError: 'NOMBRE_DE_COLUMNA'",
     "donde": "Cualquier script",
     "causa": "El archivo o la pestaña de origen ya no tiene esa columna (cambió el formato del reporte).",
     "accion": "Compara los encabezados del archivo nuevo con el anterior y corrige el nombre en el origen."},
    {"sintoma": "APIError 429 / 503 de Google, o «Quota exceeded»",
     "donde": "Lectura de Sheets",
     "causa": "Límite temporal de Google o servicio caído.",
     "accion": "Espera 10 a 15 minutos y vuelve a ejecutar. No dispares varias veces seguidas."},
    {"sintoma": "invalid_grant / Token has been expired or revoked",
     "donde": "Scripts que usan Drive (paquetes, certificados, Kuepa Empleo, mantenimiento de appends)",
     "causa": "El token de Drive (credentials_module.json) venció o pertenece a una cuenta desactivada.",
     "accion": "Regenera el token con tu cuenta (_reorg/regenerar_token.py) y actualiza SECRETS_BUNDLE del repo."},
    {"sintoma": "GitHub 401: Bad credentials",
     "donde": "Botón Ejecutar (panel y manual)",
     "causa": "Venció el token de GitHub que usa el dashboard.",
     "accion": "Crea un token nuevo (fine-grained, Actions: Read and write) y reemplaza ops.github_token "
               "en los Secrets de Streamlit Cloud."},
    {"sintoma": "GitHub 404: no existe ops_run_script.yml",
     "donde": "Botón Ejecutar",
     "causa": "El repo de esa fila del CATALOGO no tiene el workflow, o el token no tiene acceso a ese repo.",
     "accion": "Revisa la columna repo del CATALOGO y que el token incluya ese repositorio."},
    {"sintoma": "n8n 403 Prohibido",
     "donde": "Botones de flujos n8n",
     "causa": "El token X-OPS-TOKEN del dashboard no coincide con el del webhook en n8n.",
     "accion": "Igualar ops.n8n_token (Streamlit) con la credencial Header Auth del webhook en n8n."},
    {"sintoma": "n8n 503 «Database is not ready!» o sin conexión con n8n",
     "donde": "Botones de flujos n8n",
     "causa": "El servidor n8n.kuepa.com está caído.",
     "accion": "No es un problema del flujo: avisa al administrador del servidor y reintenta después."},
    {"sintoma": "«Falta la URL del webhook ...»",
     "donde": "Botones de flujos n8n",
     "causa": "La llave webhook_key del CATALOGO no está en los Secrets [ops.n8n_webhooks].",
     "accion": "Agrega la URL de producción del webhook en los Secrets de Streamlit y reinicia la app."},
    {"sintoma": "Los correos de remisiones salen sin PDF o el flujo se detiene en «Convertidor a PDF»",
     "donde": "Remisiones STC 3.0 (n8n)",
     "causa": "El servicio de PDF (túnel cloudflared) está apagado o cambió de URL.",
     "accion": "Abre de nuevo el túnel desde STC\\ y actualiza la URL en el nodo «Convertidor a PDF Correo»."},
    {"sintoma": "TIMEOUT",
     "donde": "Cualquier script",
     "causa": "La ejecución superó el tiempo máximo (columna timeout_min del CATALOGO).",
     "accion": "Si el volumen de datos creció, sube timeout_min en el CATALOGO; si no, revisa si quedó "
               "esperando un recurso (Drive, sitio web)."},
]
