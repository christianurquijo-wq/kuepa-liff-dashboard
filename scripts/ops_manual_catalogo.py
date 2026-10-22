"""
Agrega las columnas del MANUAL al CATALOGO del Sheet de operaciones y llena
un borrador de cada ficha (redactado a partir del código de cada script).

    python scripts/ops_manual_catalogo.py <ID_DEL_SHEET> [ruta_service_account.json]

Reglas (para no pisar el trabajo del equipo):
  - Si una columna del manual no existe, se agrega al final del encabezado.
  - Solo se escribe en celdas VACÍAS. Lo que alguien ya editó en el Sheet se respeta.
  - Las filas cuyo id no esté en FICHAS se listan al final como "sin ficha".

Columnas del manual (todas texto libre; el manual del dashboard las lee tal cual):
  para_que_sirve   qué resuelve, en lenguaje de negocio
  cuando_usarla    cuándo corre sola y cuándo conviene dispararla a mano
  entrada          de dónde lee, separado por ";"  -> alimenta el diagrama
  salida           dónde escribe, separado por ";" -> alimenta el diagrama
  si_falla         qué revisar primero si falla

Prefijos en entrada/salida (definen la forma del nodo en el diagrama):
  Sheet: · BigQuery: · Drive: · Correo: · Firestore: · Web: · Dashboard: · Proceso:
"""
from __future__ import annotations

import sys

import gspread
from gspread.utils import rowcol_to_a1

COLUMNAS_MANUAL = ["para_que_sirve", "cuando_usarla", "entrada", "salida", "si_falla"]

# ---------------------------------------------------------------- textos reutilizables
NOCHE = ("Corre sola todas las noches dentro del lote nocturno. Dispárala a mano solo si "
         "acabas de corregir datos en el Sheet y necesitas verlos ya en los tableros.")
FALLA_CARGA = ("1) Si el error dice que las columnas no coinciden, alguien cambió, agregó o borró "
               "un encabezado en la pestaña de origen: restaura el nombre o avisa a Datos para "
               "ajustar la tabla. 2) Si es un error 429/503 de Google, espera 10 minutos y reintenta. "
               "3) Si el error menciona una columna concreta (KeyError), esa columna cambió de nombre.")
REEMPLAZA = "Reemplaza la tabla completa en BigQuery con lo que tenga hoy el Sheet (no acumula historia)."


def carga(que: str, sheet: str, pestana: str, tabla: str, extra: str = "",
          cuando: str = NOCHE, si_falla: str = FALLA_CARGA) -> dict:
    return {
        "para_que_sirve": f"Lleva {que} de la pestaña «{pestana}» del Sheet «{sheet}» a BigQuery, "
                          f"para que los tableros y consultas trabajen con datos actualizados. {REEMPLAZA}"
                          + (f" {extra}" if extra else ""),
        "cuando_usarla": cuando,
        "entrada": f"Sheet: {sheet} › {pestana}",
        "salida": f"BigQuery: EFE_2026.{tabla}",
        "si_falla": si_falla,
    }


ECO = "SEGUIMIENTO ECOLOMBIA +"
CONV = "CONVOCATORIA ECOLOMBIA +"
JAE = "SEGUIMIENTO ACADÉMICO TÉCNICOS EFE JAE"
COL = "CONTROL DE SEGUIMIENTO COLSUBSIDIO"
COL2 = "Seguimiento Colsubsidio 2.0"
SUBA = "Seguimiento Metas Suba es Oportunidad"
SUBA_EMP = "Empleabilidad Suba es Oportunidad"
SUBA_LOOK = "DataLookerProyectoSuba"
SUBA_ENC = "Encuesta de satisfacción Suba es Oportunidad (respuestas)"
STC_GEN = "Seguimiento General STC3.0"
STC_FORM = "Seguimiento Formación STC3.0"
FCS = "Consolidado FCS"

FICHAS: dict[str, dict] = {
    # ------------------------------------------------------------ Lotes
    "efe-lote-nocturno": {
        "para_que_sirve": "Ejecuta de una sola vez TODAS las cargas diarias de EFE (Ecolombia, JAE, "
                          "Colsubsidio y Suba): primero respalda las tablas históricas y luego pasa cada "
                          "Sheet a BigQuery. Es el 'botón de actualizar todo'.",
        "cuando_usarla": "Corre sola cada noche (23:00). Úsala a mano solo si la corrida nocturna falló "
                         "o si hubo correcciones grandes en varios Sheets. Tarda entre 15 y 40 minutos.",
        "entrada": "Proceso: Mantenimiento de appends; Sheet: Sheets de EFE (ECO, JAE, Colsubsidio, Suba)",
        "salida": "BigQuery: EFE_2026 (todas las tablas de seguimiento); Correo: alerta de fallos",
        "si_falla": "Mira en 'Análisis de ejecuciones' cuál script falló: el lote sigue con los demás y "
                    "solo reporta los que fallaron. Corrige ese script y dispáralo solo, no todo el lote.",
    },
    "efe-lote-bitacoras": {
        "para_que_sirve": "Actualiza las bitácoras de seguimiento de ECO+ y JAE en BigQuery "
                          "(registro de contactos y gestiones con los estudiantes).",
        "cuando_usarla": "Corre sola cada mañana (09:30). Úsala a mano cuando el equipo termine de "
                         "registrar gestiones y necesite verlas antes del día siguiente.",
        "entrada": f"Sheet: Datalake_ECO › BITÁCORAS; Sheet: {JAE} › Bitacoras",
        "salida": "BigQuery: EFE_2026.bitacora_ECOPLUS_2026; BigQuery: EFE_2026.bitacora_JAE_2026",
        "si_falla": FALLA_CARGA,
    },
    # ------------------------------------------------------------ Mantenimiento
    "efe-mantenimiento": {
        "para_que_sirve": "Protege la historia: copia a Drive (CSV) las tablas históricas APPEND y "
                          "RECUPERACIONES de BigQuery y, si alguna expiró, la restaura desde esa copia.",
        "cuando_usarla": "Corre sola al inicio del lote nocturno. A mano solo si una tabla histórica "
                         "desapareció de BigQuery.",
        "entrada": "BigQuery: EFE_2026 (tablas *_APPEND y RECUPERACIONES_*)",
        "salida": "Drive: TABLAS_APPEND_BAKCUP; Drive: APPEND RECUPERACIONES (JAE & ECO)",
        "si_falla": "Si el error habla de Drive o 'invalid_grant', el token de Drive (credentials_module.json) "
                    "venció o es de otra persona: regenéralo con tu cuenta. Las dos carpetas de respaldo "
                    "deben ser de una cuenta activa de Kuepa.",
    },
    "efe-append-mensual": {
        "para_que_sirve": "Toma la foto del mes: agrega el corte actual de cada tabla 'Unificado' a su "
                          "tabla histórica *_APPEND, para poder comparar mes a mes.",
        "cuando_usarla": "UNA vez al mes, al cierre. No la repitas: si corre dos veces, duplica el mes "
                         "en la historia.",
        "entrada": "BigQuery: EFE_2026 (tablas Unificado_*)",
        "salida": "BigQuery: EFE_2026 (tablas *_APPEND)",
        "si_falla": "Antes de reintentar revisa en BigQuery si el mes ya quedó cargado (para no duplicar). "
                    "Si quedó a medias, borra solo las filas de la fecha de hoy y vuelve a correrla.",
    },
    # ------------------------------------------------------------ Ecolombia
    "eco-upload": carga("el seguimiento general de los estudiantes", ECO, "SEGUIMIENTO", "ECOPLUS_V2_2026",
                        "Es la base de Recuperaciones ECO+."),
    "eco-bitacora": carga("las bitácoras de gestión", "Datalake_ECO", "BITÁCORAS", "bitacora_ECOPLUS_2026",
                          cuando="Corre sola a las 09:30 (lote de bitácoras). A mano cuando el equipo "
                                 "termine de registrar gestiones."),
    "eco-caracterizacion": carga("la encuesta de caracterización", CONV, "Caracterización",
                                 "ECOPLUS_2026_Caracterizacion"),
    "eco-satisfaccion": carga("las respuestas de satisfacción (NPS)", ECO, "NPS", "Satisfaccion_ECOPLUS_2026"),
    "eco-empleabilidad": carga("el seguimiento de empleabilidad", ECO, "EMPLEABILIDAD",
                               "ECOPLUS_2026_Empleabilidad"),
    "eco-vacantes": carga("las vacantes de patrocinio", ECO, "VACANTES DE PATROCINIO",
                          "VACANTES_PATROCINIO_ECOPLUS_2026",
                          si_falla="Si aparece una columna '________' es que el encabezado de la columna A "
                                   "quedó vacío; el script ya lo renombra a 'vacante'. " + FALLA_CARGA),
    "eco-recuperaciones": {
        "para_que_sirve": "Toma la foto diaria de los estudiantes activos de ECO+ y los clasifica en "
                          "'Al día', 'Con pendientes académicos' o 'Pendiente por ingresar', guardando "
                          "la historia día a día.",
        "cuando_usarla": "Corre sola cada noche, DESPUÉS de 'ECO+ · Seguimiento'. Si la corres dos veces "
                         "el mismo día, reemplaza la foto de ese día (no duplica).",
        "entrada": "BigQuery: EFE_2026.ECOPLUS_V2_2026",
        "salida": "BigQuery: EFE_2026.RECUPERACIONES_ECOPLUS_2026",
        "si_falla": "Revisa primero que 'ECO+ · Seguimiento' haya corrido bien: esta lee su tabla.",
    },
    "eco-convocatoria": carga("el avance de la convocatoria (fase 1)", CONV, "SEGUIMIENTO FASE 1",
                              "ECOPLUS_2026_CONVOCATORIA"),
    # ------------------------------------------------------------ JAE
    "jae-upload": carga("la base general de estudiantes", JAE, "BASE GENERAL", "JAE_V2_2026",
                        "Es la base de Recuperaciones JAE."),
    "jae-bitacora": carga("las bitácoras de gestión", JAE, "Bitacoras", "bitacora_JAE_2026",
                          cuando="Corre sola a las 09:30 (lote de bitácoras). A mano cuando el equipo "
                                 "termine de registrar gestiones."),
    "jae-caracterizacion": carga("la encuesta de caracterización", JAE, "Caracterización",
                                 "JAE_2026_Caracterizacion"),
    "jae-satisfaccion": carga("las respuestas de satisfacción", JAE, "Satisfacción", "Satisfaccion_JAE_2026"),
    "jae-empleabilidad": carga("el seguimiento de empleabilidad", JAE, "Empleabilidad", "JAE_2026_Empleabilidad"),
    "jae-vacantes": carga("las vacantes de patrocinio", JAE, "VACANTES DE PATROCINIO",
                          "VACANTES_PATROCINIO_JAE_2026"),
    "jae-recuperaciones": {
        "para_que_sirve": "Toma la foto diaria de los estudiantes activos de JAE y su estado académico "
                          "('Al día', 'Con pendientes', 'Pendiente por ingresar'), guardando la historia.",
        "cuando_usarla": "Corre sola cada noche, DESPUÉS de 'JAE · Base general'. Repetirla el mismo día "
                         "reemplaza la foto de ese día.",
        "entrada": "BigQuery: EFE_2026.JAE_V2_2026",
        "salida": "BigQuery: EFE_2026.RECUPERACIONES_JAE_2026",
        "si_falla": "Revisa primero que 'JAE · Base general' haya corrido bien: esta lee su tabla.",
    },
    # ------------------------------------------------------------ Colsubsidio
    "col-upload": carga("el seguimiento de participantes", COL, "primera pestaña", "COLSUBSIDIO_2026_V2"),
    "col2-upload": carga("el seguimiento de participantes (cohorte 2.0)", COL2, "SEGUIMIENTO GENERAL",
                         "COLSUBSIDIO_2_0_2026_V2"),
    "col-caracterizacion": carga("la encuesta de caracterización", COL, "Caracterización",
                                 "COLSUBSIDIO_2026_Caracterizacion"),
    "col2-caracterizacion": carga("la encuesta de caracterización (cohorte 2.0)", COL2, "Caracterización",
                                  "COLSUBSIDIO_2_0_2026_Caracterizacion"),
    "col-satisfaccion": carga("las respuestas de satisfacción", COL, "Satisfacción",
                              "COLSUBSIDIO_2026_Satisfaccion"),
    "col2-satisfaccion": carga("las respuestas de satisfacción (cohorte 2.0)", COL2, "Satisfacción",
                               "COLSUBSIDIO_2_0_2026_Satisfaccion"),
    "col2-backfill": {
        "para_que_sirve": "Carga histórica única (backfill) de Colsubsidio 2.0 con fecha fija 2026-06-01.",
        "cuando_usarla": "No usar: ya cumplió su función. Se deja solo como referencia.",
        "entrada": f"Sheet: {COL2}", "salida": "BigQuery: EFE_2026 (tablas APPEND de Colsubsidio 2.0)",
        "si_falla": "No aplica.",
    },
    # ------------------------------------------------------------ Suba
    "suba-upload": carga("la base de atención de participantes", SUBA, "BASE DE ATENCIÓN", "SUBA_2026_V2"),
    "suba-caracterizacion": carga("las respuestas del formulario de caracterización (CRM)", SUBA,
                                  "Respuestas formulario CRM", "SUBA_2026_Caracterización"),
    "suba-satisfaccion": carga("las respuestas de la encuesta de satisfacción", SUBA_ENC, "Hoja 1",
                               "Suba_2026_Satisfaccion"),
    "suba-empleabilidad": carga("el seguimiento de empleabilidad", SUBA_EMP, "Empleabilidad",
                                "SUBA_2026_Empleabilidad"),
    "suba-metas-emp": carga("las metas de empleabilidad", SUBA_LOOK, "MetasEmpleabilidadBigQuery",
                            "SUBA_2026_METAS_EMPLEABILIDAD"),
    "suba-metas-form": carga("las metas de formación", SUBA_LOOK, "Parámetros", "SUBA_2026_METAS_FORMACION"),
    "suba-unificado": carga("el consolidado de formación", SUBA_LOOK, "UnificadoFormacion",
                            "SUBA_2026_UnificadoFormacion"),
    "suba-form-basico": {
        "para_que_sirve": "Carga de formación nivel básico de Suba (versión anterior al Unificado).",
        "cuando_usarla": "Pendiente de confirmar si sigue vigente; hoy no corre en el lote.",
        "entrada": f"Sheet: {SUBA}", "salida": "BigQuery: EFE_2026 (formación básico Suba)",
        "si_falla": "No habilitar sin confirmar con el equipo de Suba.",
    },
    "suba-form-inav": {
        "para_que_sirve": "Carga de formación nivel intermedio/avanzado de Suba (versión anterior al Unificado).",
        "cuando_usarla": "Pendiente de confirmar si sigue vigente; hoy no corre en el lote.",
        "entrada": f"Sheet: {SUBA}", "salida": "BigQuery: EFE_2026 (formación InAv Suba)",
        "si_falla": "No habilitar sin confirmar con el equipo de Suba.",
    },
    # ------------------------------------------------------------ STC 3.0
    "stc-upload": {
        "para_que_sirve": "Pasa el Seguimiento General de STC 3.0 a BigQuery. Es la tabla que alimenta "
                          "el Dashboard de STC (Overview, Hitos, Matriz). " + REEMPLAZA,
        "cuando_usarla": "Dispárala cuando el equipo de STC haya actualizado el Seguimiento General y "
                         "necesite ver los cambios en el dashboard.",
        "entrada": f"Sheet: {STC_GEN} › SEGUIMIENTO GENERAL",
        "salida": "BigQuery: EFE_2026.STC_3_0_V2_2026; Dashboard: Dashboard STC 3.0",
        "si_falla": FALLA_CARGA,
    },
    "stc-paquetes": {
        "para_que_sirve": "Arma el paquete de evidencia de cada participante: une su certificado con el "
                          "pantallazo del SIS en un solo PDF, lo sube a la carpeta de paquetes y deja el "
                          "enlace en la pestaña CERTIFICADOS.",
        "cuando_usarla": "Después de que se carguen certificados y pantallazos nuevos y antes de enviar "
                         "entregables. Puede tardar varios minutos (procesa PDFs).",
        "entrada": f"Sheet: {STC_FORM} › CERTIFICADOS; Drive: carpeta de pantallazos (1.SIS)",
        "salida": f"Drive: CONSOLIDADOS (paquetes PDF); Sheet: {STC_FORM} › CERTIFICADOS",
        "si_falla": "Si menciona Drive o 'invalid_grant', el token de Drive venció: regenéralo con tu "
                    "cuenta. Si un participante no tiene pantallazo, el script lo salta: revisa la carpeta 1.SIS.",
    },
    "stc-fechas-cert": {
        "para_que_sirve": "Lee la fecha de expedición de cada certificado PDF y la escribe en la pestaña "
                          "CERTIFICADOS, para controlar plazos.",
        "cuando_usarla": "Cuando se suban certificados nuevos. Normalmente antes de 'Paquetes de certificados'.",
        "entrada": f"Sheet: {STC_FORM} › CERTIFICADOS; Drive: certificados PDF",
        "salida": f"Sheet: {STC_FORM} › CERTIFICADOS",
        "si_falla": "Si un certificado no tiene texto legible (escaneado como imagen) no se puede leer la "
                    "fecha: complétala a mano. Errores de Drive: regenerar token.",
    },
    "stc-auditoria-ia": {
        "para_que_sirve": "Revisa con IA (Gemini) los paquetes de certificados y marca posibles "
                          "inconsistencias antes de entregarlos.",
        "cuando_usarla": "Antes de un entregable, cuando quieras una revisión automática de calidad. "
                         "Consume la API de Gemini (costo por uso).",
        "entrada": f"Sheet: {STC_FORM} › CERTIFICADOS; Drive: paquetes PDF",
        "salida": f"Sheet: {STC_FORM} › CERTIFICADOS (resultado de auditoría)",
        "si_falla": "Pendiente: hay que corregir la ruta 'AUDITORIA_PAQIETES' antes de habilitarla. Si "
                    "falla por cuota, revisa la clave de Gemini.",
    },
    "stc-kuepa-empleo": {
        "para_que_sirve": "Toma el reporte más reciente de la plataforma Kuepa Empleo (archivo de la carpeta "
                          "REPORTES KUEPA EMPLEO) y actualiza la pestaña REPORTE_KUEPA_EMPLEO del Consolidado FCS.",
        "cuando_usarla": "Cada vez que se deje un reporte nuevo de Kuepa Empleo en la carpeta.",
        "entrada": "Drive: REPORTES KUEPA EMPLEO; Sheet: archivo LOCALIDADES",
        "salida": f"Sheet: {FCS} › REPORTE_KUEPA_EMPLEO",
        "si_falla": "Si falla con KeyError (por ejemplo PROFILE_DOC_NUMBER), cambió el formato del reporte "
                    "o del archivo LOCALIDADES: revisa los encabezados. Errores de Drive: regenerar token.",
    },
    "stc-kuepa-empleo-ent": {
        "para_que_sirve": "Igual que 'BD Kuepa Empleo', pero arma la versión para entregas (formato del "
                          "entregable al cliente).",
        "cuando_usarla": "Antes de preparar un entregable de empleabilidad.",
        "entrada": "Drive: REPORTES KUEPA EMPLEO",
        "salida": "Sheet: Hoja de entrega Kuepa Empleo",
        "si_falla": "Mismas causas que 'BD Kuepa Empleo': formato del reporte o token de Drive.",
    },
    "stc-subsanaciones": {
        "para_que_sirve": "Cruza el reporte de Kuepa Empleo contra el Consolidado FCS y lista lo que hay "
                          "que subsanar (diferencias por participante) en SUBSANACIONES_KUEPA_EMPLEO.",
        "cuando_usarla": "Después de 'BD Kuepa Empleo', cuando necesites la lista de correcciones.",
        "entrada": f"Sheet: {FCS} › CONSOLIDADO; Sheet: {FCS} › REPORTE_KUEPA_EMPLEO",
        "salida": f"Sheet: {FCS} › SUBSANACIONES_KUEPA_EMPLEO",
        "si_falla": "Revisa primero que 'BD Kuepa Empleo' haya corrido: esta usa su resultado.",
    },
    "stc-discrepancias": {
        "para_que_sirve": "Compara el reporte de empleabilidad contra Kuepa Empleo y registra las discrepancias.",
        "cuando_usarla": "Pendiente de habilitar: lee una pestaña ('REPORTE KUEPA_EMPLEO', con espacio) que "
                         "probablemente no existe.",
        "entrada": f"Sheet: {FCS} › ENTREGA 1; Sheet: {FCS} › REPORTE EMPLEABILIDAD",
        "salida": "Sheet: Reporte_Discrepancias",
        "si_falla": "Valida el nombre exacto de las pestañas antes de habilitar.",
    },
    "stc-correos-pdf": {
        "para_que_sirve": "Generaba PDFs de los correos enviados como evidencia. Reemplazado por el flujo "
                          "de remisiones en n8n.",
        "cuando_usarla": "No usar (solo funciona en un PC con Windows).",
        "entrada": "Correo: Gmail", "salida": "Drive: evidencias PDF",
        "si_falla": "No aplica.",
    },
    "stc-bot1": {
        "para_que_sirve": "Robot que entra al SIS y toma pantallazos de notas y asistencia por participante.",
        "cuando_usarla": "Pendiente: tiene usuario y contraseña del SIS escritos en el código; hay que "
                         "moverlos a secretos y cambiar la clave antes de habilitarlo.",
        "entrada": "Web: SIS", "salida": "Drive: 1.SIS (pantallazos)",
        "si_falla": "No habilitar hasta corregir lo de la contraseña.",
    },
    # ------------------------------------------------------------ Otros
    "512-sql": {
        "para_que_sirve": "Genera las sentencias SQL de los casos de la consulta modular 512 Avanza.",
        "cuando_usarla": "Pendiente: hoy deja el .sql en el equipo donde corre; en GitHub se pierde. "
                         "Hay que adaptarlo para guardarlo en Drive o en una tabla.",
        "entrada": "Sheet: casos 512 Avanza", "salida": "Proceso: archivo casos_sql_generados.sql",
        "si_falla": "Contiene datos personales: nunca subir el .sql al repositorio.",
    },
    "col-inst-permisos": {
        "para_que_sirve": "Sincroniza quién puede entrar a la app de Instancias Colsubsidio: crea a los "
                          "tutores como administradores y a los estudiantes como usuarios permitidos.",
        "cuando_usarla": "Cuando cambie la asignación de tutores o entren estudiantes nuevos. Cambia "
                         "accesos reales: confirma antes de ejecutar.",
        "entrada": "Sheet: asignación de grupos y estudiantes (Hoja 1)",
        "salida": "Firestore: administradores y usuarios permitidos",
        "si_falla": "Revisa que el Sheet tenga las columnas Correo y Codigo grupo. Ojo: hoy la clave de "
                    "cada tutor es su propio correo; conviene cambiar ese esquema.",
    },
    "col-inst-backup": {
        "para_que_sirve": "Respalda las respuestas guardadas en Firebase de Instancias Colsubsidio.",
        "cuando_usarla": "Antes de cualquier cambio masivo en la app y de forma periódica.",
        "entrada": "Firestore: respuestas", "salida": "Sheet: respaldo de respuestas",
        "si_falla": "Verifica que existan los archivos de credenciales de Firebase.",
    },
    "col-inst-recovery": {
        "para_que_sirve": "Restaura las respuestas en Firebase a partir del Sheet de recuperación.",
        "cuando_usarla": "Solo para recuperar datos después de un incidente. SOBRESCRIBE lo que haya en Firebase.",
        "entrada": "Sheet: recuperación de respuestas", "salida": "Firestore: respuestas (Firebase C)",
        "si_falla": "Corre primero el backup para no perder lo actual.",
    },
    "col-inst-compara": {
        "para_que_sirve": "Valida que los correos de la app coincidan con los del Sheet de Colsubsidio.",
        "cuando_usarla": "Pendiente: busca un archivo de credenciales que no existe (firebase_credentials.json).",
        "entrada": "Firestore: usuarios; Sheet: base Colsubsidio", "salida": "Proceso: reporte en consola",
        "si_falla": "Corregir la ruta de credenciales antes de habilitar.",
    },
    "adres-consulta": {
        "para_que_sirve": "Consulta en la web de ADRES la afiliación a salud de una lista de cédulas y "
                          "guarda el resultado en un Sheet.",
        "cuando_usarla": "Pendiente de probar en GitHub: el sitio puede bloquear la consulta o pedir captcha.",
        "entrada": "Sheet: lista de cédulas; Web: ADRES", "salida": "Sheet: resultado de afiliación",
        "si_falla": "Si aparece captcha o bloqueo, no reintentes en bucle: córrelo desde un PC.",
    },
    "divisor-acj": {
        "para_que_sirve": "Separa documentos escaneados (ACJ / cédulas) en un PDF por persona y los "
                          "organiza en Drive.",
        "cuando_usarla": "Pendiente: necesita una lista de cédulas como entrada; falta leerla desde un Sheet.",
        "entrada": "Drive: documentos escaneados; Proceso: lista de cédulas",
        "salida": "Drive: un PDF por persona",
        "si_falla": "Revisa que la cuenta de servicio tenga acceso a la carpeta de Drive.",
    },
    # ------------------------------------------------------------ n8n
    "n8n-remisiones": {
        "para_que_sirve": "Envía a las empresas los correos de remisión de participantes de STC 3.0, con "
                          "el PDF de evidencia adjunto, y registra el envío.",
        "cuando_usarla": "Cuando el equipo de STC tenga remisiones listas en el Sheet REMISIONES. Envía "
                         "correos reales: confirma antes de ejecutar.",
        "entrada": "Sheet: REMISIONES; Proceso: servicio de PDF (túnel)",
        "salida": "Correo: empresas; Sheet: REMISIONES (estado de envío)",
        "si_falla": "Lo más común: el túnel del servicio de PDF está apagado o cambió su URL (actualízala "
                    "en n8n). Si n8n responde 503, el servidor de n8n está caído: avisa al administrador.",
    },
}


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Uso: python scripts/ops_manual_catalogo.py <ID_DEL_SHEET> [ruta_service_account.json]")
    sa = sys.argv[2] if len(sys.argv) > 2 else "service_account.json"
    ws = gspread.service_account(filename=sa).open_by_key(sys.argv[1]).worksheet("CATALOGO")
    valores = ws.get_all_values()
    if not valores:
        sys.exit("CATALOGO vacío: corre primero scripts/ops_setup_sheet.py")

    encabezado = valores[0]
    nuevas = [c for c in COLUMNAS_MANUAL if c not in encabezado]
    if nuevas:
        encabezado = encabezado + nuevas
        if ws.col_count < len(encabezado):
            ws.add_cols(len(encabezado) - ws.col_count)
        ws.update(range_name="A1", values=[encabezado])
        print(f"[+] columnas agregadas: {', '.join(nuevas)}")

    idx = {c: encabezado.index(c) for c in COLUMNAS_MANUAL}
    col_id = encabezado.index("id")
    primera, ultima = min(idx.values()), max(idx.values())
    bloque, llenadas, sin_ficha = [], 0, []
    for fila in valores[1:]:
        fila = fila + [""] * (len(encabezado) - len(fila))
        ficha = FICHAS.get(fila[col_id].strip(), {})
        if fila[col_id].strip() and not ficha:
            sin_ficha.append(fila[col_id])
        for col in COLUMNAS_MANUAL:
            if not fila[idx[col]].strip() and ficha.get(col):
                fila[idx[col]] = ficha[col]
                llenadas += 1
        bloque.append(fila[primera:ultima + 1])

    if bloque:
        rango = f"{rowcol_to_a1(2, primera + 1)}:{rowcol_to_a1(len(bloque) + 1, ultima + 1)}"
        ws.update(range_name=rango, values=bloque, value_input_option="RAW")
    print(f"[ok] {llenadas} celdas del manual llenadas (las que ya tenían texto no se tocaron)")
    if sin_ficha:
        print(f"[i] filas sin borrador (complétalas en el Sheet): {', '.join(sin_ficha)}")


if __name__ == "__main__":
    main()
