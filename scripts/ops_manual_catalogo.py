"""
Agrega las columnas del MANUAL al CATALOGO del Sheet de operaciones y llena
un borrador de cada ficha (redactado a partir del código de cada script).

    python scripts/ops_manual_catalogo.py <ID_DEL_SHEET> [ruta_service_account.json]

Reglas (para no pisar el trabajo del equipo):
  - Si una columna del manual no existe, se agrega al final del encabezado.
  - Solo se escribe en celdas VACÍAS. Lo que alguien ya editó en el Sheet se respeta.
  - --reescribir=id1,id2 fuerza a reemplazar las fichas de esas filas con el texto de este archivo.
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
        "entrada": "Sheet: REMISIONES › Modelo n8n; Proceso: servicio de PDF (túnel)",
        "salida": "Correo: empresas (cuenta Socios 3.0); Drive: PDF de evidencia del correo; Sheet: REMISIONES › Modelo n8n (fecha y PDF de envío)",
        "si_falla": "Lo más común: el túnel del servicio de PDF está apagado o cambió su URL (actualízala "
                    "en n8n). Si n8n responde 503, el servidor de n8n está caído: avisa al administrador.",
    },
    # ------------------------------------------------------------ n8n (redactadas desde los flujos exportados, oct-2026)
    "data-bq-formacion": {
        "para_que_sirve": "Trae de BigQuery (plataforma Kuepa/SIS) la actividad de los participantes de formación de "
                          "STC 3.0: componentes vistos, asistencias, sesiones, accesos, estadísticas por usuario y notas "
                          "publicadas, y reescribe esas pestañas del Sheet de formación.",
        "cuando_usarla": "Corre sola todos los días a las 06:00. Dispárala a mano si necesitas el avance de formación "
                         "al momento (por ejemplo, antes de preparar el entregable de LOGS).",
        "entrada": "BigQuery: Kuepa SIS (logs, asistencias, sesiones, accesos, notas)",
        "salida": "Sheet: Seguimiento Formación STC3.0 › LOGS; Sheet: Seguimiento Formación STC3.0 › SESIONES; Sheet: Seguimiento Formación STC3.0 › ASISTENCIAS; Sheet: Seguimiento Formación STC3.0 › LOG_ACCESS; "
                  "Sheet: Seguimiento Formación STC3.0 › USER_STATISTICS; Sheet: Seguimiento Formación STC3.0 › NOTAS PUBLICADAS",
        "si_falla": "Cada pestaña se borra y se vuelve a llenar: si falla a mitad, alguna puede quedar vacía; vuelve a "
                    "ejecutarlo. Si el error es de permisos de Google, revisa la credencial de Google Sheets conectada en n8n.",
    },
    "Reporte_CRM": {
        "para_que_sirve": "Actualiza SOLO la pestaña «Reporte CRM» del Seguimiento General de STC 3.0 con los leads del CRM "
                          "traídos de BigQuery. Es la versión rápida de «Reportes STC 3.0».",
        "cuando_usarla": "Cuando el equipo necesita ver leads nuevos del CRM durante el día sin esperar la corrida de "
                         "las 06:00 ni refrescar todos los reportes.",
        "entrada": "BigQuery: Kuepa CRM (leads STC 3.0)",
        "salida": "Sheet: Seguimiento General STC3.0 › Reporte CRM",
        "si_falla": "La pestaña se borra antes de escribir: si falla, vuelve a ejecutar. n8n 503 = servidor caído; "
                    "403 = token X-OPS-TOKEN distinto entre el dashboard y n8n.",
    },
    "reportes-STC3.0": {
        "para_que_sirve": "Refresca de una vez todos los reportes CRM y SIS de STC 3.0 desde BigQuery y los reparte en "
                          "los Sheets de cada equipo: Seguimiento General (Reporte CRM/SIS), Formación (REPORTE CRM/SIS), "
                          "Verificación (Leads CRM), Anexo 3 FSC (REPORTE CRM/SIS) y una copia de respaldo en Data SIS-CRM.",
        "cuando_usarla": "Corre sola todos los días a las 06:00. A mano cuando hubo cambios grandes en CRM o SIS y "
                         "varios equipos necesitan datos frescos.",
        "entrada": "BigQuery: Kuepa CRM; BigQuery: Kuepa SIS",
        "salida": "Sheet: Seguimiento General STC3.0 › Reporte CRM / Reporte SIS; Sheet: Seguimiento Formación STC3.0 › REPORTE CRM / REPORTE SIS; "
                  "Sheet: Seguimiento Verificación STC3.0 › Leads CRM; Sheet: Anexo 3 FSC › REPORTE - CRM / REPORTE SIS; "
                  "Sheet: Data SIS-CRM STC3.0 (respaldo)",
        "si_falla": "Primero borra y luego escribe cada pestaña: si falla a mitad, alguna puede quedar vacía; vuelve a "
                    "ejecutarlo completo. Tarda varios minutos.",
    },
    "cierre-formacion-stc3.0": {
        "para_que_sirve": "Envía el correo de cierre de ruta de formación a los participantes que ya terminaron y aún "
                          "no lo han recibido, y marca «COMUNICADO FINALIZACIÓN RUTA = ENVIADA» en el consolidado.",
        "cuando_usarla": "Corre sola una vez al día. A mano después de actualizar estados de formación, cuando quieras "
                         "que los comunicados salgan de inmediato. Envía correos reales: confirma antes de ejecutar.",
        "entrada": "Sheet: Seguimiento Formación STC3.0 › CONSOLIDADO",
        "salida": "Correo: participantes (cuenta Socios 3.0); Sheet: Seguimiento Formación STC3.0 › CONSOLIDADO (marca de envío)",
        "si_falla": "No reenvía a quien ya tiene la marca ENVIADA, así que es seguro reintentar. Si Gmail rechaza "
                    "envíos, revisa el límite diario de la cuenta o la credencial de Gmail en n8n.",
    },
    "envio-certificados-stc3.0": {
        "para_que_sirve": "Envía a cada participante CERTIFICADO su certificado en PDF (lo descarga del enlace en el "
                          "consolidado) y marca el envío para no repetirlo.",
        "cuando_usarla": "Cuando se carguen certificados nuevos (columna «Link Certificado»). Envía correos reales con "
                         "adjunto: confirma antes de ejecutar.",
        "entrada": "Sheet: Seguimiento Formación STC3.0 › CONSOLIDADO; Drive: certificados PDF",
        "salida": "Correo: participantes con certificado adjunto; Sheet: Seguimiento Formación STC3.0 › CONSOLIDADO (marca de envío)",
        "si_falla": "Si un enlace de certificado está vacío o sin permisos, ese participante falla: corrige el enlace "
                    "y reintenta (los ya enviados no se repiten).",
    },
    "correo-bienvenida-stc3.0": {
        "para_que_sirve": "Envía las comunicaciones HTML de STC 3.0 a quien aún no las ha recibido: invitación a la ruta "
                          "de empleabilidad (básica o especializada), invitación a formación y credenciales de acceso a "
                          "las sesiones. Marca cada envío en su lista.",
        "cuando_usarla": "Corre sola de lunes a viernes a las 10:30. A mano cuando cargues una lista nueva de "
                         "participantes. Envía correos reales: confirma antes de ejecutar.",
        "entrada": "Sheet: Archivo cargue CRM; Sheet: Asignación atención Cohorte II SDDE; Sheet: Seguimiento Formación STC3.0 › CONSOLIDADO",
        "salida": "Correo: participantes (cuenta Socios 3.0); Sheet: listas de origen (marca Enviado); "
                  "Sheet: Seguimiento Formación STC3.0 › SESIONES",
        "si_falla": ("Solo envía a filas con Enviado = falso, así que reintentar no duplica. Si Gmail rechaza "
                    "envíos, revisa el límite diario de la cuenta o su credencial en n8n."),
    },
    "vrd-fcs-stc3.0": {
        "para_que_sirve": "Trae de BigQuery el estado de verificación (VRD) y de orientación (FCS) de cada participante "
                          "en el SIS y lo deja en el Seguimiento General para cruzarlo con la gestión del equipo.",
        "cuando_usarla": "Corre sola todos los días a las 06:00. A mano después de cargas masivas de orientaciones.",
        "entrada": "BigQuery: Kuepa SIS (verificación y orientación)",
        "salida": "Sheet: Seguimiento General STC3.0 › REPORTE VRD/FCS - SIS; Sheet: Consolidado FCS › REPORTE FCS - SIS",
        "si_falla": "Las pestañas se borran antes de escribir: si falla, vuelve a ejecutarlo para que no queden vacías. "
                    "Si el error es de permisos, revisa la credencial de Google conectada en n8n.",
    },
    "documentos-suba": {
        "para_que_sirve": "Organiza las evidencias de las obligaciones del contrato Suba es Oportunidad: por cada fila "
                          "del listado de entregables descarga el documento (PDF de un Sheet/Doc o archivo de Drive) y lo "
                          "copia en la carpeta de Drive de la obligación correspondiente.",
        "cuando_usarla": "Antes de un entregable o informe de obligaciones de Suba, cuando el listado tenga documentos nuevos.",
        "entrada": "Sheet: Entregables_SUBA_PP › Hoja 5; Drive: documentos de evidencia",
        "salida": "Drive: carpetas de obligaciones Suba; Sheet: Entregables_SUBA_PP › Hoja 5 (marca de procesado)",
        "si_falla": "Si un documento no se puede descargar, revisa que el enlace sea válido y compartido con la cuenta "
                    "de Drive conectada en n8n (Google Drive - SUBA).",
    },
    "reporte-logs-sdde-formacion-stc3.0": {
        "para_que_sirve": "Arma el entregable de LOGS para la SDDE: cruza los participantes del consolidado de formación "
                          "con su actividad en BigQuery, llena la hoja «Entregable LOGS», copia la plantilla a la carpeta "
                          "de entregables y envía el reporte por correo.",
        "cuando_usarla": "Al cierre de cada corte de reporte a la SDDE. Conviene correr antes «LOGSSTC3.0-FORMACIÓN».",
        "entrada": "Sheet: Seguimiento Formación STC3.0 › CONSOLIDADO; BigQuery: Kuepa SIS (logs)",
        "salida": "Sheet: Entregable LOGS › Hoja 1; Drive: carpeta de entregables (copia de plantilla); "
                  "Correo: Reporte LOGS - Entrega",
        "si_falla": ("Si el correo no llega, revisa la credencial de Gmail (Socios 3.0) en n8n. Si falla al copiar "
                    "la plantilla, verifica que la plantilla y la carpeta de entregables sigan existiendo."),
    },
    "actualizar-notas-eco": {
        "para_que_sirve": "Copia las notas y la asistencia del grupo HyT de Ecolombia+ (Sheet de notas del grupo) a las "
                          "pestañas de respaldo del Seguimiento ECO+, para que el seguimiento tenga el dato académico al día.",
        "cuando_usarla": "Corre sola todos los días a las 15:00. A mano cuando los docentes terminen de registrar notas o asistencia.",
        "entrada": "Sheet: NOTAS Y ASISTENCIA ECOLOMBIA + GRUPO HT_1 › NOTAS; Sheet: NOTAS Y ASISTENCIA ECOLOMBIA + GRUPO HT_1 › ASISTENCIA",
        "salida": "Sheet: SEGUIMIENTO ECOLOMBIA + › NOTAS BACKUP HyT; Sheet: SEGUIMIENTO ECOLOMBIA + › ASISTENCIA BACKUP HyT",
        "si_falla": "Si cambian columnas en el Sheet de notas del grupo, el cruce falla: revisa encabezados en ambos Sheets.",
    },
    "asistencias-jae": {
        "para_que_sirve": "Trae de BigQuery las asistencias modulares y las bitácoras de JAE y reescribe esas dos pestañas "
                          "del Seguimiento JAE. La pestaña Bitacoras es la que luego sube a BigQuery «JAE · Bitácora».",
        "cuando_usarla": "Corre sola todos los días a las 04:30 (antes del lote de bitácoras de las 09:30). A mano si "
                         "necesitas asistencias del día.",
        "entrada": "BigQuery: Kuepa SIS (asistencias y bitácoras JAE)",
        "salida": "Sheet: SEGUIMIENTO ACADÉMICO TÉCNICOS EFE JAE › BD Asistencias Modulares; "
                  "Sheet: SEGUIMIENTO ACADÉMICO TÉCNICOS EFE JAE › Bitacoras",
        "si_falla": "Las pestañas se borran antes de escribir: si falla, vuelve a ejecutarlo para que no queden vacías.",
    },
    "notas-modulares-jae": {
        "para_que_sirve": "Trae de BigQuery los resultados de notas por módulo de los estudiantes de JAE y reescribe la "
                          "pestaña BD Notas Modulares del Seguimiento JAE (por lotes, para no saturar Google Sheets).",
        "cuando_usarla": "Corre sola todos los días a las 05:00. A mano cuando se publiquen notas nuevas.",
        "entrada": "BigQuery: Kuepa SIS (notas modulares JAE)",
        "salida": "Sheet: SEGUIMIENTO ACADÉMICO TÉCNICOS EFE JAE › BD Notas Modulares",
        "si_falla": "Si se corta a mitad, la pestaña queda incompleta: vuelve a ejecutarlo completo.",
    },
    "consultas-colsubsidio": {
        "para_que_sirve": "Refresca el control de seguimiento de Colsubsidio TICS 2.0 con los reportes del CRM, del SIS y "
                          "de asistencia (BigQuery) y agrega a SEGUIMIENTO GENERAL a las personas nuevas que llegan del listado SISE.",
        "cuando_usarla": "Programado cada 3 horas (en la versión exportada estaba inactivo: confirma en n8n). A mano "
                         "cuando necesites el seguimiento de Colsubsidio al momento.",
        "entrada": "BigQuery: Kuepa CRM; BigQuery: Kuepa SIS (asistencia); Sheet: listado SISE",
        "salida": "Sheet: CONTROL DE SEGUIMIENTO COLSUBSIDIO TICS 2.0 › Reporte CRM / Reporte SIS / AsistenciaSIS; "
                  "Sheet: CONTROL DE SEGUIMIENTO COLSUBSIDIO TICS 2.0 › SEGUIMIENTO GENERAL",
        "si_falla": "Las pestañas de reporte se borran antes de escribir: si falla, vuelve a ejecutarlo.",
    },
}


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--reescribir")]
    reescribir: set[str] = set()
    for a in sys.argv[1:]:
        if a.startswith("--reescribir="):
            reescribir |= {x.strip() for x in a.split("=", 1)[1].split(",") if x.strip()}
    if not args:
        sys.exit("Uso: python scripts/ops_manual_catalogo.py <ID_DEL_SHEET> [service_account.json] "
                 "[--reescribir=id1,id2]")
    sa = args[1] if len(args) > 1 else "service_account.json"
    ws = gspread.service_account(filename=sa).open_by_key(args[0]).worksheet("CATALOGO")
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
            forzar = fila[col_id].strip() in reescribir
            if (forzar or not fila[idx[col]].strip()) and ficha.get(col) and fila[idx[col]] != ficha[col]:
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
