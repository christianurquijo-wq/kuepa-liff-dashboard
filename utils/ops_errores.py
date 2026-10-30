"""
Catálogo de errores en lenguaje práctico (oct-2026).

Para quien usa el Panel de control, el Manual o las páginas de EFE sin ser técnico: traduce mensajes
como «GitHub 404: ...» o «Bad int64 value: #N/A» a qué pasó, qué puede hacer esa persona y si
debe reportarlo. Un SOLO catálogo para todo el dashboard:
  - mostrar(...)          bloque explicado donde ocurre el error (con detalle técnico plegado
                          y botón «Reportar»).
  - render_catalogo(...)  la página Operaciones › Errores frecuentes y la pestaña del Manual.
  - diagnosticar(texto)   la entrada del catálogo que corresponde a un mensaje (lógica pura).

Reportar: deja una fila en la pestaña REPORTES_ERRORES del Sheet de operaciones (siempre) y manda
un correo al equipo si están configurados en los secrets:
    [ops.correo]  gmail_user = "...", gmail_app_password = "...", para = "..."
(los mismos GMAIL_USER / GMAIL_APP_PASSWORD / OPS_ALERT_EMAIL de las alertas de los scripts).

Para agregar un error: suma un dict a CATALOGO (los patrones son expresiones regulares sin
distinguir mayúsculas; el primero que coincide gana, así que los más específicos van primero).
"""
from __future__ import annotations

import hashlib
import re
import smtplib
from datetime import datetime
from email.message import EmailMessage

DISPARO = "Al ejecutar un botón"
AUTOMATIZACION = "Cuando la automatización corre"
DASHBOARD = "En las páginas del dashboard"
CATEGORIAS = [DISPARO, AUTOMATIZACION, DASHBOARD]

REPORTA = "Usa el botón **Reportar**: le llega al equipo con todo el detalle."

CATALOGO: list[dict] = [
    # ------------------------------------------------------------------ al ejecutar un botón
    {"id": "pin", "categoria": DISPARO, "codigos": "PIN",
     "patrones": [r"PIN incorrecto"],
     "titulo": "El PIN no es correcto",
     "que_paso": "Esta automatización es sensible (cambia datos o envía correos) y pide un PIN para confirmar.",
     "que_hacer": ["Vuelve a escribir el PIN con cuidado.", "Si no lo tienes, pídeselo a Christian."],
     "reportar": False},
    {"id": "sin_permiso_cuenta", "categoria": DISPARO, "codigos": "Acceso",
     "patrones": [r"no está autorizada"],
     "titulo": "Tu cuenta no tiene permiso para ejecutar",
     "que_paso": "Iniciaste sesión, pero tu correo no está en la lista de personas que pueden ejecutar.",
     "que_hacer": ["Verifica que entraste con tu cuenta de Kuepa (no la personal).",
                   "Pide acceso a Christian."],
     "reportar": False},
    {"id": "gh_401", "categoria": DISPARO, "codigos": "401",
     "patrones": [r"GitHub 401", r"Bad credentials"],
     "titulo": "El panel perdió su permiso en GitHub",
     "que_paso": "La «llave» que usa el panel para encender las automatizaciones en GitHub venció o fue "
                 "revocada. No es algo que hiciste tú.",
     "que_hacer": ["No sirve reintentar: va a fallar igual hasta que se renueve la llave.", REPORTA],
     "reportar": True},
    {"id": "gh_limite", "categoria": DISPARO, "codigos": "403 · 429",
     "patrones": [r"rate limit", r"GitHub 429", r"secondary rate"],
     "titulo": "Demasiadas solicitudes seguidas a GitHub",
     "que_paso": "GitHub frena por unos minutos cuando recibe muchas solicitudes en poco tiempo.",
     "que_hacer": ["Espera 5 a 10 minutos y vuelve a intentar una sola vez.",
                   "Evita hacer varios clics seguidos en el mismo botón."],
     "reportar": False},
    {"id": "gh_403", "categoria": DISPARO, "codigos": "403",
     "patrones": [r"GitHub 403", r"Resource not accessible"],
     "titulo": "El panel no tiene permiso sobre esa automatización",
     "que_paso": "La llave del panel funciona, pero no incluye el repositorio o el permiso que necesita esta "
                 "automatización (por ejemplo, una automatización nueva o un repositorio que cambió).",
     "que_hacer": ["No sirve reintentar.", REPORTA],
     "reportar": True},
    {"id": "gh_404", "categoria": DISPARO, "codigos": "404",
     "patrones": [r"GitHub 404"],
     "titulo": "GitHub no encuentra la automatización",
     "que_paso": "El panel buscó la automatización en GitHub y no la encontró: puede que el repositorio "
                 "cambió de nombre, que falte subir un archivo o que la llave no vea ese repositorio.",
     "que_hacer": ["No sirve reintentar.", REPORTA],
     "reportar": True},
    {"id": "gh_422", "categoria": DISPARO, "codigos": "422",
     "patrones": [r"GitHub 422", r"workflow_dispatch", r"Unexpected inputs"],
     "titulo": "La automatización tiene un problema de configuración en GitHub",
     "que_paso": "GitHub recibió la orden pero la rechazó porque el archivo de configuración de la "
                 "automatización tiene un error (por ejemplo, después de una edición reciente).",
     "que_hacer": ["No sirve reintentar.", REPORTA],
     "reportar": True},
    {"id": "gh_5xx", "categoria": DISPARO, "codigos": "500 · 502 · 503",
     "patrones": [r"GitHub 5\d\d"],
     "titulo": "GitHub está teniendo problemas",
     "que_paso": "El error viene del lado de GitHub, no del panel ni de la automatización.",
     "que_hacer": ["Espera 10 a 15 minutos y vuelve a intentar.",
                   "Puedes ver si GitHub está con fallas en githubstatus.com."],
     "reportar": False},
    {"id": "webhook_falta", "categoria": DISPARO, "codigos": "Configuración",
     "patrones": [r"Falta la URL del webhook"],
     "titulo": "A esta automatización le falta su dirección de conexión",
     "que_paso": "El panel no sabe a dónde enviar la orden de este flujo de n8n: falta configurarlo.",
     "que_hacer": ["No sirve reintentar.", REPORTA],
     "reportar": True},
    {"id": "n8n_403", "categoria": DISPARO, "codigos": "401 · 403",
     "patrones": [r"n8n 40[13]", r"Authorization data is wrong", r"Prohibido"],
     "titulo": "n8n rechazó la orden del panel",
     "que_paso": "El flujo en n8n pide una clave y la del panel no coincide (alguien cambió la credencial "
                 "del flujo o se copió sin ella).",
     "que_hacer": ["No sirve reintentar.", REPORTA],
     "reportar": True},
    {"id": "n8n_404", "categoria": DISPARO, "codigos": "404",
     "patrones": [r"n8n 404", r"not registered", r"webhook .*not found"],
     "titulo": "El flujo de n8n está apagado o cambió",
     "que_paso": "n8n no tiene activo ese flujo (está en «Inactive») o su dirección cambió.",
     "que_hacer": ["Si tienes acceso a n8n: abre el flujo y actívalo (interruptor «Active»), luego reintenta.",
                   "Si no tienes acceso: " + REPORTA[0].lower() + REPORTA[1:]],
     "reportar": True},
    {"id": "n8n_caido", "categoria": DISPARO, "codigos": "500 · 502 · 503 · 504",
     "patrones": [r"n8n 5\d\d", r"N8nNoDisponible", r"Database is not ready", r"Bad Gateway",
                  r"Service Unavailable", r"Gateway Time"],
     "titulo": "El servidor de n8n está caído o saturado",
     "que_paso": "El problema es del servidor de n8n (n8n.kuepa.com), no del flujo ni de lo que hiciste.",
     "que_hacer": ["Espera 10 a 15 minutos y vuelve a intentar una sola vez.",
                   "Si sigue igual por más de una hora, " + REPORTA[0].lower() + REPORTA[1:]],
     "reportar": False},
    {"id": "sin_conexion", "categoria": DISPARO, "codigos": "Sin respuesta",
     "patrones": [r"Sin conexión con", r"sin conexión", r"ConnectionError", r"ConnectTimeout", r"ReadTimeout",
                  r"timed out", r"Max retries exceeded"],
     "titulo": "No hubo respuesta del servicio",
     "que_paso": "El panel no logró comunicarse con GitHub o n8n: puede ser la conexión o que el servicio "
                 "esté lento en este momento.",
     "que_hacer": ["Revisa tu conexión a internet.", "Espera unos minutos y vuelve a intentar."],
     "reportar": False},

    # ------------------------------------------------------------------ cuando la automatización corre
    {"id": "timeout", "categoria": AUTOMATIZACION, "codigos": "TIMEOUT",
     "patrones": [r"\bTIMEOUT\b", r"tiempo máximo", r"exceeded the maximum execution time"],
     "titulo": "La automatización tardó más de lo permitido",
     "que_paso": "Se detuvo porque superó su tiempo máximo. Suele pasar cuando la hoja creció mucho o un "
                 "servicio (Drive, un sitio web) estuvo lento.",
     "que_hacer": ["Vuelve a ejecutarla una vez.", "Si vuelve a pasar, " + REPORTA[0].lower() + REPORTA[1:]],
     "reportar": False},
    {"id": "pestana", "categoria": AUTOMATIZACION, "codigos": "Hoja",
     "patrones": [r"WorksheetNotFound", r"No encuentro la pestaña", r"worksheet .*not found"],
     "titulo": "No encontró una pestaña de la hoja de Google",
     "que_paso": "Alguien cambió el nombre de una pestaña (o la borró) en la hoja que usa la automatización.",
     "que_hacer": ["Revisa en la hoja que la pestaña conserve su nombre original (mayúsculas y tildes incluidas).",
                   "Corrígelo y vuelve a ejecutar. Si no sabes cuál es, " + REPORTA[0].lower() + REPORTA[1:]],
     "reportar": False},
    {"id": "columnas", "categoria": AUTOMATIZACION, "codigos": "Columnas",
     "patrones": [r"no tiene las siguientes columnas", r"columnas que no son de BQ", r"KeyError",
                  r"not in index", r"__index_level_0__", r"________"],
     "titulo": "Cambiaron las columnas de la hoja",
     "que_paso": "La hoja de origen tiene una columna nueva, borrada, renombrada o sin título. La automatización "
                 "se detiene a propósito para no dañar la información.",
     "que_hacer": ["Revisa si alguien cambió encabezados de la hoja recientemente.",
                   "Si fue un error, deja el encabezado como estaba y vuelve a ejecutar.",
                   "Si el cambio es a propósito, " + REPORTA[0].lower() + REPORTA[1:]],
     "reportar": False},
    {"id": "drive_credenciales", "categoria": DASHBOARD, "codigos": "403",
     "patrones": [r"Drive credentials", r"Permission denied while getting Drive", r"Access Denied.*Drive"],
     "titulo": "La consulta no puede leer una hoja de Google vinculada",
     "que_paso": "Los datos vienen de una hoja de Google conectada a BigQuery y esa hoja no está compartida "
                 "con la cuenta del dashboard.",
     "que_hacer": ["Comparte la hoja vinculada como Lector con la cuenta del dashboard.", REPORTA],
     "reportar": True},
    {"id": "hoja_permiso", "categoria": AUTOMATIZACION, "codigos": "403 · 404",
     "patrones": [r"SpreadsheetNotFound", r"PERMISSION_DENIED", r"caller does not have permission",
                  r"File not found"],
     "titulo": "La automatización ya no puede abrir una hoja o carpeta",
     "que_paso": "La hoja o carpeta de Google dejó de estar compartida con la cuenta de la automatización, "
                 "se movió o se borró.",
     "que_hacer": ["Si sabes qué hoja es: compártela de nuevo como Editor con la cuenta de la automatización "
                   "(el correo que termina en iam.gserviceaccount.com).", REPORTA],
     "reportar": True},
    {"id": "na_formula", "categoria": AUTOMATIZACION, "codigos": "#N/A",
     "patrones": [r"#N/A", r"#REF!", r"#VALUE!", r"#DIV/0!", r"Bad (int64|double|numeric) value",
                  r"Could not (convert|parse)", r"Invalid (date|timestamp)"],
     "titulo": "Una celda tiene un error de fórmula o texto donde va un número",
     "que_paso": "En alguna hoja hay celdas con #N/A, #REF! o texto en una columna de números o fechas, y "
                 "BigQuery no puede leerlas.",
     "que_hacer": ["Busca #N/A (Ctrl+F) en la hoja del proyecto y corrige esa celda.",
                   "Si es una fórmula, envuélvela así: =SI.ERROR(tu_fórmula; \"\").",
                   "Vuelve a ejecutar o espera la carga de la noche."],
     "reportar": False},
    {"id": "bq_no_existe", "categoria": AUTOMATIZACION, "codigos": "404",
     "patrones": [r"Not found: (Table|Dataset|View)", r"was not found in location"],
     "titulo": "No se encontró una tabla de datos",
     "que_paso": "La tabla de BigQuery no existe o venció (en la versión gratuita las tablas se borran a los "
                 "60 días si no se renuevan). Normalmente se recupera sola en la carga de la noche.",
     "que_hacer": ["Espera a mañana y revisa de nuevo.", "Si sigue igual al día siguiente, "
                   + REPORTA[0].lower() + REPORTA[1:]],
     "reportar": False},
    {"id": "token_drive", "categoria": AUTOMATIZACION, "codigos": "Permiso vencido",
     "patrones": [r"invalid_grant", r"Token has been expired", r"token .*revoked"],
     "titulo": "Venció el permiso de Google Drive de la automatización",
     "que_paso": "La automatización usa un permiso de Drive que se renueva cada cierto tiempo y ya venció.",
     "que_hacer": ["No sirve reintentar.", REPORTA],
     "reportar": True},
    {"id": "cuota", "categoria": AUTOMATIZACION, "codigos": "429",
     "patrones": [r"Quota exceeded", r"RATE_LIMIT_EXCEEDED", r"Too Many Requests", r"\b429\b",
                  r"RESOURCE_EXHAUSTED"],
     "titulo": "Se alcanzó un límite de uso de Google",
     "que_paso": "Google limita cuántas lecturas o consultas se hacen por minuto (o por día, en la IA). Es "
                 "temporal.",
     "que_hacer": ["Espera 10 a 15 minutos y vuelve a ejecutar una sola vez.",
                   "Si es la auditoría con IA, espera al día siguiente."],
     "reportar": False},
    {"id": "pdf_tunel", "categoria": AUTOMATIZACION, "codigos": "PDF",
     "patrones": [r"Convertidor a PDF", r"crear-pdf", r"trycloudflare"],
     "titulo": "El servicio que arma los PDF no está disponible",
     "que_paso": "Los PDF de evidencia se generan en un servicio que corre en el computador de Christian; "
                 "si está apagado, el flujo no puede crear los PDF.",
     "que_hacer": ["No sirve reintentar hasta que el servicio esté encendido.", REPORTA],
     "reportar": True},
    {"id": "libreria", "categoria": AUTOMATIZACION, "codigos": "Instalación",
     "patrones": [r"ModuleNotFoundError", r"No module named"],
     "titulo": "Falta un componente para ejecutar la automatización",
     "que_paso": "El entorno donde corre la automatización no tiene instalado algo que necesita "
                 "(típicamente después de un cambio en el código).",
     "que_hacer": ["No sirve reintentar.", REPORTA],
     "reportar": True},
    {"id": "n8n_paso", "categoria": AUTOMATIZACION, "codigos": "Paso en rojo",
     "patrones": [r"Nodo «", r"node .*error", r"n8n status: (error|crashed)"],
     "titulo": "Falló un paso del flujo de n8n",
     "que_paso": "El flujo arrancó pero uno de sus pasos falló. El detalle técnico dice cuál (texto entre « »).",
     "que_hacer": ["Si el paso habla de una hoja, correo o credencial, revisa que siga compartida o vigente.",
                   "Reintenta una vez; si vuelve a fallar en el mismo paso, " + REPORTA[0].lower() + REPORTA[1:]],
     "reportar": False},
]

CATALOGO.append(
    {"id": "sin_detalle", "categoria": AUTOMATIZACION, "codigos": "FALLIDO",
     "patrones": [r"^\s*FALLIDO\s*$"],
     "titulo": "La automatización terminó con error, sin detalle registrado",
     "que_paso": "La ejecución falló pero no dejó un mensaje que explique la causa (pasa cuando se corta "
                 "antes de escribirlo).",
     "que_hacer": ["Abre «Ver ejecución» en la tarjeta para ver qué pasó, si tienes acceso.",
                   "Reintenta una vez; si vuelve a fallar, " + REPORTA[0].lower() + REPORTA[1:]],
     "reportar": False})

GENERICO = {"id": "generico", "categoria": "", "codigos": "–", "patrones": [],
            "titulo": "Ocurrió un error no identificado",
            "que_paso": "Este mensaje todavía no está en el catálogo de errores frecuentes.",
            "que_hacer": ["Reintenta una vez.", REPORTA], "reportar": True}


def diagnosticar(texto: str) -> dict:
    t = str(texto or "")
    for e in CATALOGO:
        if any(re.search(p, t, flags=re.I) for p in e["patrones"]):
            return e
    return GENERICO


# ------------------------------------------------------------------ Streamlit
def _clave(texto: str, contexto: str) -> str:
    return hashlib.md5(f"{contexto}|{texto}".encode()).hexdigest()[:10]


def reportar(entrada: dict, texto: str, contexto: str, usuario: str = "") -> tuple[bool, str]:
    """Fila en REPORTES_ERRORES (siempre) + correo al equipo si está configurado."""
    import streamlit as st

    from utils.ops_data import TZ, _cliente, _sheet_id

    ahora = datetime.now(TZ).isoformat(timespec="seconds")
    fila = [ahora, usuario or "anónimo", contexto, entrada["id"], entrada["titulo"], str(texto)[:2000]]
    guardado = False
    try:
        libro = _cliente().open_by_key(_sheet_id())
        try:
            ws = libro.worksheet("REPORTES_ERRORES")
        except Exception:  # noqa: BLE001 -- primera vez: se crea
            ws = libro.add_worksheet("REPORTES_ERRORES", rows=200, cols=6)
            ws.update(range_name="A1", values=[["fecha", "usuario", "donde", "error_id", "titulo", "detalle"]])
        ws.append_row(fila, value_input_option="RAW")
        guardado = True
    except Exception:  # noqa: BLE001
        pass

    correo = dict(dict(st.secrets.get("ops", {})).get("correo", {}))
    enviado = False
    if correo.get("gmail_user") and correo.get("gmail_app_password") and correo.get("para"):
        try:
            msg = EmailMessage()
            msg["Subject"] = f"[Panel] Error reportado: {entrada['titulo']}"
            msg["From"], msg["To"] = correo["gmail_user"], correo["para"]
            msg.set_content(f"Fecha: {ahora}\nUsuario: {usuario or 'anónimo'}\nDónde: {contexto}\n"
                            f"Error identificado: {entrada['titulo']} ({entrada['id']})\n\nDetalle técnico:\n{texto}")
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
                s.login(correo["gmail_user"], correo["gmail_app_password"])
                s.send_message(msg)
            enviado = True
        except Exception:  # noqa: BLE001
            pass
    if enviado:
        return True, "Reporte enviado al equipo por correo. Gracias."
    if guardado:
        return True, "Reporte registrado. El equipo lo revisa en la hoja de reportes."
    return False, "No se pudo enviar el reporte. Copia el detalle técnico y envíaselo a Christian."


def mostrar(texto: str, contexto: str, usuario: str = "", compacto: bool = False) -> None:
    """Bloque explicado: qué pasó, qué hacer, detalle técnico plegado y botón Reportar."""
    import streamlit as st

    e = diagnosticar(texto)
    clave = _clave(texto, contexto)
    with st.container(border=True):
        st.markdown(f"**⚠️ {e['titulo']}**")
        st.markdown(e["que_paso"])
        if not compacto or e["que_hacer"]:
            st.markdown("**Qué puedes hacer:**\n" + "\n".join(f"- {p}" for p in e["que_hacer"]))
        with st.expander("Detalle técnico (para soporte)"):
            st.code(str(texto)[:1500], language="text")
        enviados = st.session_state.setdefault("ops_reportes_enviados", set())
        if clave in enviados:
            st.caption("✔ Ya reportaste este error.")
        elif st.button("📨 Reportar al equipo", key=f"rep_{clave}",
                       type="primary" if e["reportar"] else "secondary"):
            ok, msg = reportar(e, texto, contexto, usuario)
            if ok:
                enviados.add(clave)
            (st.success if ok else st.warning)(msg)


def guardar_pendiente(texto: str, contexto: str) -> None:
    """Lo usa el botón Ejecutar: guarda el error y recarga, para mostrarlo explicado arriba de la página
    (antes solo salía un aviso flotante que desaparecía en segundos)."""
    import streamlit as st

    st.session_state["ops_error_pendiente"] = {"texto": texto, "contexto": contexto}


def mostrar_pendiente(usuario: str = "") -> None:
    import streamlit as st

    pend = st.session_state.get("ops_error_pendiente")
    if not pend:
        return
    mostrar(pend["texto"], pend["contexto"], usuario)
    if st.button("Cerrar este aviso", key="ops_error_cerrar"):
        st.session_state.pop("ops_error_pendiente", None)
        st.rerun()


def render_catalogo(prefijo: str = "cat") -> None:
    """Catálogo completo con buscador y un probador de mensajes."""
    import streamlit as st

    c1, c2 = st.columns([2, 1.2])
    q = c1.text_input("Buscar", placeholder="ej. 404, PIN, columnas, n8n, #N/A…", key=f"{prefijo}_q")
    cat = c2.selectbox("Dónde aparece", ["Todos"] + CATEGORIAS, key=f"{prefijo}_cat")
    with st.expander("🔎 ¿Tienes un mensaje de error? Pégalo aquí y te digo qué significa"):
        pegado = st.text_area("Mensaje", key=f"{prefijo}_pegado", height=90,
                              placeholder="ej. GitHub 404: no existe ops_run_script.yml en ...")
        if pegado.strip():
            e = diagnosticar(pegado)
            st.markdown(f"**{e['titulo']}**  \n{e['que_paso']}")
            st.markdown("**Qué puedes hacer:**\n" + "\n".join(f"- {p}" for p in e["que_hacer"]))

    lista = [e for e in CATALOGO
             if (cat == "Todos" or e["categoria"] == cat)
             and (not q.strip() or q.strip().lower() in
                  " ".join([e["titulo"], e["que_paso"], e["codigos"], " ".join(e["que_hacer"]),
                            " ".join(e["patrones"])]).lower())]
    if not lista:
        st.info("No hay errores que coincidan. Si te apareció uno nuevo, usa el probador de arriba.")
    for categoria in CATEGORIAS:
        grupo = [e for e in lista if e["categoria"] == categoria]
        if not grupo:
            continue
        st.markdown(f"#### {categoria}")
        for e in grupo:
            etiqueta = ("🔴 " if e["reportar"] else "🟡 ") + f"{e['titulo']}  ·  `{e['codigos']}`"
            with st.expander(etiqueta):
                st.markdown(f"**Qué pasó:** {e['que_paso']}")
                st.markdown("**Qué puedes hacer:**\n" + "\n".join(f"- {p}" for p in e["que_hacer"]))
    st.caption("🔴 requiere que lo resuelva el equipo (repórtalo) · 🟡 normalmente lo puedes resolver tú "
               "o se resuelve solo esperando.")
