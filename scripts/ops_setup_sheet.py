"""
Crea (o completa) el Google Sheet del Panel de Operaciones.

Pasos previos (una sola vez):
  1. Crea un Google Sheet vacío llamado "OPS_Control_Automatizaciones".
  2. Compártelo como EDITOR con el client_email de service_account.json
     (la misma cuenta de servicio que usa el dashboard).
  3. Desde la raíz del repo kuepa-liff-dashboard, con el venv activo:
        python scripts/ops_setup_sheet.py <ID_DEL_SHEET>

Qué hace:
  - Crea las pestañas CATALOGO, LOG_EJECUCIONES y SOLICITUDES con sus encabezados.
  - Si CATALOGO está vacío, lo llena con el inventario inicial (abajo).
    Si ya tiene filas, NO lo toca (tus ediciones manuales mandan).

El CATALOGO es la fuente de verdad del panel: agregar un botón nuevo = agregar
una fila. Columnas clave:
  plataforma   github | n8n
  script       github: ruta relativa a la raíz del repo, o "lote:nocturno" / "lote:bitacoras"
               n8n: ID del workflow en n8n (para cruzar con la bitácora)
  workflow     archivo del workflow de GitHub (ops_run_script.yml / ops_lotes.yml)
  webhook_key  n8n: nombre de la llave en st.secrets["ops"]["n8n_webhooks"]
  cwd          script | root  (directorio de trabajo del script)
  sensible     SI -> pide PIN antes de ejecutar
  activo       SI -> aparece como botón; NO -> sale en "Pendientes" con el motivo
  frecuencia_horas  cada cuántas horas DEBERÍA correr (0 = solo manual). Se usa
                    para detectar automatizaciones atrasadas.
"""
from __future__ import annotations

import sys

import gspread

COLUMNAS_CATALOGO = [
    "id", "nombre", "proyecto", "plataforma", "repo", "script", "workflow",
    "webhook_key", "cwd", "timeout_min", "frecuencia", "frecuencia_horas",
    "sensible", "activo", "responsable", "descripcion",
]
COLUMNAS_LOG = [  # mismo orden que runner/ops_logger.py -> COLUMNAS
    "id_ejecucion", "request_id", "fecha_inicio", "fecha_fin", "duracion_seg",
    "plataforma", "repo", "automatizacion_id", "script", "origen",
    "disparado_por", "estado", "codigo_salida", "error", "run_url", "lote",
]
COLUMNAS_SOLICITUDES = [
    "request_id", "fecha", "usuario", "automatizacion_id", "nombre",
    "plataforma", "resultado", "detalle",
]

EFE = "EFE_2026"
STC = "STC3.0-automatizaciones"
RS = "ops_run_script.yml"
LT = "ops_lotes.yml"
DIARIO = ("Diario 23:00 (lote nocturno)", 24)
MANUAL = ("Manual", 0)


def _f(id_, nombre, proyecto, repo, script, *, workflow=RS, cwd="script", timeout=60,
       frec=MANUAL, sensible="NO", activo="SI", descripcion="", plataforma="github", webhook_key=""):
    return [id_, nombre, proyecto, plataforma, repo, script, workflow, webhook_key, cwd,
            timeout, frec[0], frec[1], sensible, activo, "Christian Urquijo", descripcion]


CATALOGO_INICIAL = [
    # ---- Lotes (equivalen a los crons de ProyectDash) ----
    _f("efe-lote-nocturno", "Lote nocturno EFE (todas las cargas)", "EFE 2026", EFE, "lote:nocturno",
       workflow=LT, timeout=180, frec=DIARIO, sensible="SI",
       descripcion="Corre Mantenimiento_appends y luego todas las cargas Sheets→BigQuery (trigger.py)."),
    _f("efe-lote-bitacoras", "Lote bitácoras ECO + JAE", "EFE 2026", EFE, "lote:bitacoras",
       workflow=LT, timeout=30, frec=("Diario 09:30", 24),
       descripcion="bitacora_ECO + bitacora_JAE (trigger_bitacora.py)."),
    # ---- EFE: mantenimiento ----
    _f("efe-mantenimiento", "Backup/restauración tablas APPEND", "EFE 2026", EFE, "Mantenimiento_appends.py",
       frec=DIARIO, descripcion="Respalda tablas APPEND/RECUPERACIONES en Drive y las restaura si expiraron (sandbox BQ)."),
    _f("efe-append-mensual", "Snapshot mensual APPEND", "EFE 2026", EFE, "Append_DATA_BQ.py",
       frec=("Mensual (manual)", 720), sensible="SI",
       descripcion="Agrega el corte del mes a las tablas *_APPEND. Correr 1 vez al mes: si se repite, duplica."),
    # ---- ECO+ / Ecolombia ----
    _f("eco-upload", "ECO+ · Seguimiento", "Ecolombia", EFE, "Upload_ECO++_2026.py", frec=DIARIO),
    _f("eco-bitacora", "ECO+ · Bitácora", "Ecolombia", EFE, "bitacora_ECO.py", frec=("Diario 09:30 y 23:00", 12)),
    _f("eco-caracterizacion", "ECO+ · Caracterización", "Ecolombia", EFE, "Caracterizacion_ECO_2026.py", frec=DIARIO),
    _f("eco-satisfaccion", "ECO+ · Satisfacción (NPS)", "Ecolombia", EFE, "Satisfaccion_ECO.py", frec=DIARIO),
    _f("eco-empleabilidad", "ECO+ · Empleabilidad", "Ecolombia", EFE, "Empleabilidad_ECO.py", frec=DIARIO),
    _f("eco-vacantes", "ECO+ · Vacantes de patrocinio", "Ecolombia", EFE, "vacantes_patrocinio_ECO.py", frec=DIARIO),
    _f("eco-recuperaciones", "ECO+ · Recuperaciones (snapshot)", "Ecolombia", EFE, "recuperaciones_ECO_APPENDS.py", frec=DIARIO),
    _f("eco-convocatoria", "ECO+ · Convocatoria fase 1", "Ecolombia", EFE, "CONVOCATORIA_ECOLOMBIA_2026.py", frec=DIARIO),
    # ---- JAE ----
    _f("jae-upload", "JAE · Base general", "JAE", EFE, "Upload_JAE_2026.py", frec=DIARIO),
    _f("jae-bitacora", "JAE · Bitácora", "JAE", EFE, "bitacora_JAE.py", frec=("Diario 09:30 y 23:00", 12)),
    _f("jae-caracterizacion", "JAE · Caracterización", "JAE", EFE, "Caracterizacion_JAE_2026.py", frec=DIARIO),
    _f("jae-satisfaccion", "JAE · Satisfacción", "JAE", EFE, "Satisfaccion_JAE_2026.py", frec=DIARIO),
    _f("jae-empleabilidad", "JAE · Empleabilidad", "JAE", EFE, "Empleabilidad_JAE_2026_V1.0.py", frec=DIARIO),
    _f("jae-vacantes", "JAE · Vacantes de patrocinio", "JAE", EFE, "vacantes_patrocinio_JAE.py", frec=DIARIO),
    _f("jae-recuperaciones", "JAE · Recuperaciones (snapshot)", "JAE", EFE, "recuperaciones_JAE_APPENDS.py", frec=DIARIO),
    # ---- Colsubsidio ----
    _f("col-upload", "Colsubsidio · Seguimiento", "Colsubsidio", EFE, "Upload Colsubsidio2026.py", frec=DIARIO),
    _f("col2-upload", "Colsubsidio 2.0 · Seguimiento", "Colsubsidio", EFE, "Upload Colsubsidio2026_2.0.py", frec=DIARIO),
    _f("col-caracterizacion", "Colsubsidio · Caracterización", "Colsubsidio", EFE, "Caracterizacion Colsubsidio2026.py", frec=DIARIO),
    _f("col2-caracterizacion", "Colsubsidio 2.0 · Caracterización", "Colsubsidio", EFE, "Caracterizacion Colsubsidio2026_2.0.py", frec=DIARIO),
    _f("col-satisfaccion", "Colsubsidio · Satisfacción", "Colsubsidio", EFE, "Satisfaccion_Colsubsidio2026.py", frec=DIARIO),
    _f("col2-satisfaccion", "Colsubsidio 2.0 · Satisfacción", "Colsubsidio", EFE, "Satisfaccion_Colsubsidio2026_2.0.py", frec=DIARIO),
    _f("col2-backfill", "Colsubsidio 2.0 · Backfill appends (colsu2)", "Colsubsidio", EFE, "colsu2.py",
       activo="NO", descripcion="One-off obsoleto (fecha fija 2026-06-01). No usar."),
    # ---- Suba ----
    _f("suba-upload", "Suba · Base de atención", "Suba", EFE, "Upload Suba2026.py", frec=DIARIO),
    _f("suba-caracterizacion", "Suba · Caracterización", "Suba", EFE, "Caracterizacion_Suba2026.py", frec=DIARIO),
    _f("suba-satisfaccion", "Suba · Satisfacción", "Suba", EFE, "Satisfaccion_Suba.py", frec=DIARIO),
    _f("suba-empleabilidad", "Suba · Empleabilidad", "Suba", EFE, "Empleabilidad_Suba2026.py", frec=DIARIO),
    _f("suba-metas-emp", "Suba · Metas empleabilidad", "Suba", EFE, "Metas_empleabilidad.py", frec=DIARIO),
    _f("suba-metas-form", "Suba · Metas formación", "Suba", EFE, "Metas_formación.py", frec=DIARIO),
    _f("suba-unificado", "Suba · Unificado formación", "Suba", EFE, "UnificadoFormacion_Suba2026.py", frec=DIARIO),
    _f("suba-form-basico", "Suba · Formación básico", "Suba", EFE, "Formacion basico Suba2026.py",
       activo="NO", descripcion="Excluido del lote por Sebastián. Confirmar si sigue vigente."),
    _f("suba-form-inav", "Suba · Formación InAv", "Suba", EFE, "Formacion InAv Suba2026.py",
       activo="NO", descripcion="Excluido del lote por Sebastián. Confirmar si sigue vigente."),
    # ---- STC 3.0 ----
    _f("stc-upload", "STC 3.0 · Seguimiento general → BQ", "STC 3.0", STC, "Upload_STC3.0/upload_STC3.0_BQ.py"),
    _f("stc-paquetes", "STC 3.0 · Paquetes de certificados", "STC 3.0", STC, "Certificados_paquetes/paquetes.py",
       timeout=120, descripcion="Une certificado + pantallazo en PDF y lo sube a Drive."),
    _f("stc-fechas-cert", "STC 3.0 · Fechas de certificados", "STC 3.0", STC, "Certificados_paquetes/fechas_certificados.py"),
    _f("stc-auditoria-ia", "STC 3.0 · Auditoría IA (Gemini)", "STC 3.0", STC, "Auditoria_paquetes/auditoria.py",
       cwd="root", timeout=120, sensible="SI", activo="NO",
       descripcion="Bug: abre 'AUDITORIA_PAQIETES/...' pero la carpeta es 'Auditoria_paquetes' (Linux distingue mayúsculas). Corregir antes de habilitar. Consume API Gemini."),
    _f("stc-kuepa-empleo", "STC 3.0 · BD Kuepa Empleo", "STC 3.0", STC, "Kuepa_empleo/bd_kuepa_empleo.py"),
    _f("stc-kuepa-empleo-ent", "STC 3.0 · BD Kuepa Empleo (entregas)", "STC 3.0", STC, "Kuepa_empleo/bd_kuepa_empleo_entrega.py"),
    _f("stc-subsanaciones", "STC 3.0 · Subsanaciones Kuepa Empleo", "STC 3.0", STC, "Kuepa_empleo/comparative.py"),
    _f("stc-discrepancias", "STC 3.0 · Discrepancias empleabilidad", "STC 3.0", STC, "Kuepa_empleo/empleabilidad.py",
       activo="NO", descripcion="Lee pestaña 'REPORTE KUEPA_EMPLEO' (con espacio) que probablemente no existe. Validar."),
    _f("stc-correos-pdf", "STC 3.0 · PDF de correos (evidencia)", "STC 3.0", STC, "Kuepa_empleo/correos.py",
       activo="NO", descripcion="Solo Windows (wkhtmltopdf en C:\\) y fecha fija. Reemplazado por el flujo n8n de remisiones."),
    _f("stc-bot1", "STC 3.0 · Bot SIS pantallazos", "STC 3.0", STC, "Bot1.py",
       activo="NO", sensible="SI",
       descripcion="Tiene usuario y contraseña del SIS escritos en el código: mover a .env y rotar la clave antes de habilitar."),
    # ---- Otros repos ----
    _f("512-sql", "512 Avanza · Generar SQL de casos", "512", "512", "main.py",
       activo="NO", descripcion="Genera un .sql local que se pierde en GitHub Actions. Adaptar para subir el archivo a Drive o crear tabla."),
    _f("col-inst-permisos", "Instancias Colsubsidio · Permisos Firestore", "Instancias Colsubsidio",
       "Instancias_colsubsidio", "main.py", sensible="SI",
       descripcion="Sincroniza administradores y usuarios permitidos (Sheet → Firestore). Cambia accesos reales."),
    _f("col-inst-backup", "Instancias Colsubsidio · Backup respuestas", "Instancias Colsubsidio",
       "Instancias_colsubsidio", "backup.py", sensible="SI"),
    _f("col-inst-recovery", "Instancias Colsubsidio · Restaurar respuestas", "Instancias Colsubsidio",
       "Instancias_colsubsidio", "recovery.py", sensible="SI",
       descripcion="Sobrescribe 'respuestas' en Firebase C desde el Sheet de recuperación."),
    _f("col-inst-compara", "Instancias Colsubsidio · Validar correos", "Instancias Colsubsidio",
       "Instancias_colsubsidio", "comparative.py",
       activo="NO", descripcion="Usa firebase_credentials.json que no existe. Corregir ruta."),
    _f("adres-consulta", "Consulta ADRES (afiliación)", "Otros", "ConsultaAdres", "consulta_adres.py",
       activo="NO", timeout=120,
       descripcion="Scraping con Playwright a un sitio del gobierno: probar primero desde GitHub (puede bloquear IPs o pedir captcha)."),
    _f("divisor-acj", "Divisor de documentos ACJ / CC", "Otros", "divisor-documentos-acj", "main.py",
       activo="NO", descripcion="Necesita una lista de cédulas como entrada. Adaptar para leerla desde un Sheet."),
    # ---- n8n ----
    _f("n8n-remisiones", "Remisiones STC 3.0 (correos + PDF)", "STC 3.0", "n8n", "ID_WORKFLOW_N8N",
       plataforma="n8n", workflow="", webhook_key="remisiones_stc", sensible="SI", activo="NO",
       descripcion="Envía correos a empresas. Requiere el servicio PDF (main.py) con URL fija. Completar ID del workflow y webhook."),
]


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Uso: python scripts/ops_setup_sheet.py <ID_DEL_SHEET> [ruta_service_account.json]")
    sheet_id = sys.argv[1]
    sa = sys.argv[2] if len(sys.argv) > 2 else "service_account.json"
    gc = gspread.service_account(filename=sa)
    sh = gc.open_by_key(sheet_id)
    existentes = {ws.title: ws for ws in sh.worksheets()}

    for nombre, columnas in (("CATALOGO", COLUMNAS_CATALOGO),
                             ("LOG_EJECUCIONES", COLUMNAS_LOG),
                             ("SOLICITUDES", COLUMNAS_SOLICITUDES)):
        ws = existentes.get(nombre) or sh.add_worksheet(nombre, rows=1000, cols=len(columnas))
        if ws.row_values(1) != columnas:
            if any(ws.row_values(1)):
                print(f"[!] {nombre}: los encabezados actuales no coinciden; revisa a mano.")
                continue
            ws.update(range_name="A1", values=[columnas])
            ws.freeze(rows=1)
        print(f"[ok] {nombre}")

    cat = sh.worksheet("CATALOGO")
    if len(cat.get_all_values()) <= 1:
        cat.append_rows(CATALOGO_INICIAL, value_input_option="RAW")
        print(f"[ok] CATALOGO llenado con {len(CATALOGO_INICIAL)} automatizaciones")
    else:
        print("[=] CATALOGO ya tenía filas: no se modificó")

    hoja1 = existentes.get("Hoja 1") or existentes.get("Sheet1")
    if hoja1 and len(sh.worksheets()) > 1 and not any(hoja1.get_all_values()):
        sh.del_worksheet(hoja1)


if __name__ == "__main__":
    main()
