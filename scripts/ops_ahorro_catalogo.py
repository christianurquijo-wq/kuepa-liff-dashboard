"""
Agrega al CATALOGO las columnas del «Ahorro de tiempo» y llena una PRIMERA estimación.

    cd C:\\Users\\Usuario50\\OneDrive\\VSC\\KuepaProyects\\Dashboard\\kuepa-liff-dashboard
    python scripts\\ops_ahorro_catalogo.py            (muestra la propuesta, no cambia nada)
    python scripts\\ops_ahorro_catalogo.py --aplicar  (crea las columnas y llena SOLO celdas vacías)

Columnas nuevas (al final del CATALOGO):
  min_ahorro_ejecucion  minutos de trabajo manual que reemplaza UNA ejecución exitosa.
                        0 = no ahorra (infraestructura o se cuenta por script, p. ej. los lotes).
                        Vacío = sin estimar (no suma; la página lo lista para que se complete).
  tope_ejecuciones_dia  máximo de ejecuciones por día que suman. Evita inflar el número cuando un
                        flujo corre varias veces al día pero a mano se haría una sola vez.
                        Vacío = sin tope.
  ahorro_estado         "Estimado" (propuesta inicial) o "Validado" (confirmado por el responsable).
  ahorro_supuesto       en qué se basa el número (para poder discutirlo).

Criterio de la propuesta (oct-2026): lo que tardaría una persona en hacer a mano lo mismo que
hace una corrida, con datos del tamaño actual: exportar/limpiar/subir una hoja, armar PDFs,
enviar correos, crear carpetas. Son ESTIMADOS: el equipo los ajusta en el Sheet y pasa la fila
a "Validado". Nunca se sobrescribe una celda ya llena.
Credenciales: [gcp_service_account] y [ops] sheet_id de .streamlit/secrets.toml.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import gspread

RAIZ = Path(__file__).resolve().parent.parent
COLUMNAS = ["min_ahorro_ejecucion", "tope_ejecuciones_dia", "ahorro_estado", "ahorro_supuesto"]

# Supuestos por tipo de tarea
CARGA = "Exportar la hoja, limpiar columnas y subirla a BigQuery a mano"
SEGUIMIENTO = "Consolidar la base de seguimiento (varias pestañas) y subirla a BigQuery"
SNAPSHOT = "Copiar el corte del día/mes a la tabla histórica a mano"
LOTE = "Se cuenta por cada script del lote (evita contar doble)"
INFRA = "Infraestructura: no reemplaza trabajo manual del equipo"
CORREOS = "Redactar/personalizar y enviar los correos uno por uno"
PDFS = "Armar y nombrar los PDF por participante y subirlos a Drive"
CARPETAS = "Crear y nombrar carpetas en Drive por participante/empresa"
REPORTE = "Armar el reporte a mano (filtrar, cruzar y formatear)"
SIS = "Consultar el SIS/CRM persona por persona y pasar los datos a la hoja"

# id -> (minutos por ejecución, tope por día, supuesto)
PROPUESTA: dict[str, tuple[float, int | None, str]] = {
    # Lotes y mantenimiento
    "efe-lote-nocturno": (0, None, LOTE),
    "efe-lote-bitacoras": (0, None, LOTE),
    "efe-mantenimiento": (10, 1, "Respaldar las tablas históricas en Drive y revisar que no hayan expirado"),
    "efe-append-mensual": (60, 1, "Cortar el mes y agregarlo a las 4 tablas históricas a mano"),
    # Ecolombia
    "eco-upload": (30, 1, SEGUIMIENTO), "eco-bitacora": (15, 2, CARGA),
    "eco-caracterizacion": (20, 1, CARGA), "eco-satisfaccion": (20, 1, CARGA),
    "eco-empleabilidad": (20, 1, CARGA), "eco-recuperaciones": (10, 1, SNAPSHOT),
    "eco-convocatoria": (20, 1, CARGA),
    "eco-vacantes": (90, 1, "Buscar vacantes en elempleo.com, filtrarlas y pasarlas a la hoja"),
    # JAE
    "jae-upload": (30, 1, SEGUIMIENTO), "jae-bitacora": (15, 2, CARGA),
    "jae-caracterizacion": (20, 1, CARGA), "jae-satisfaccion": (20, 1, CARGA),
    "jae-empleabilidad": (20, 1, CARGA), "jae-recuperaciones": (10, 1, SNAPSHOT),
    "jae-vacantes": (90, 1, "Buscar vacantes en elempleo.com, filtrarlas y pasarlas a la hoja"),
    # Colsubsidio
    "col-upload": (30, 1, SEGUIMIENTO), "col2-upload": (30, 1, SEGUIMIENTO),
    "col-caracterizacion": (20, 1, CARGA), "col2-caracterizacion": (20, 1, CARGA),
    "col-satisfaccion": (20, 1, CARGA), "col2-satisfaccion": (20, 1, CARGA),
    # Suba
    "suba-upload": (30, 1, SEGUIMIENTO), "suba-caracterizacion": (20, 1, CARGA),
    "suba-satisfaccion": (20, 1, CARGA), "suba-empleabilidad": (20, 1, CARGA),
    "suba-metas-emp": (15, 1, "Calcular las metas de empleabilidad en la hoja y subirlas"),
    "suba-metas-form": (15, 1, "Calcular las metas de formación en la hoja y subirlas"),
    "suba-unificado": (25, 1, "Unir las bases de formación de las 3 rutas y subirlas"),
    "suba-form-basico": (20, 1, CARGA), "suba-form-inav": (20, 1, CARGA),
    # STC 3.0
    "stc-upload": (30, 1, SEGUIMIENTO),
    "stc-paquetes": (120, 1, "Unir certificado + pantallazo en un PDF por participante y subirlo a Drive"),
    "stc-fechas-cert": (30, 1, "Revisar y registrar las fechas de los certificados en la hoja"),
    "stc-auditoria-ia": (180, 1, "Revisar a ojo cada paquete de certificados contra los criterios"),
    "stc-kuepa-empleo": (30, 1, CARGA), "stc-kuepa-empleo-ent": (30, 1, CARGA),
    "stc-subsanaciones": (45, 1, "Cruzar la base de Kuepa Empleo con el consolidado y listar subsanaciones"),
    "stc-discrepancias": (60, 1, "Comparar empleabilidad Kuepa vs FCS persona por persona"),
    "stc-bot1": (120, 1, "Entrar al SIS, tomar el pantallazo de notas por participante y subirlo"),
    "stc-correos-pdf": (60, 1, PDFS),
    # Otros repos
    "512-sql": (45, 1, "Armar a mano el SQL de casos del listado 512"),
    "col-inst-permisos": (30, 1, "Dar de alta administradores y usuarios en Firestore a mano"),
    "col-inst-backup": (15, 1, "Exportar las respuestas de Firebase a la hoja de respaldo"),
    "col-inst-recovery": (30, 1, "Restaurar respuestas en Firebase desde la hoja"),
    "col-inst-compara": (20, 1, "Comparar los correos del Excel contra Firebase"),
    "adres-consulta": (120, 1, "Consultar la afiliación en ADRES cédula por cédula"),
    "divisor-acj": (60, 1, "Separar el PDF consolidado en un archivo por cédula"),
    # n8n · STC 3.0
    "n8n-remisiones": (90, 1, CORREOS + " a empresas, con el PDF de evidencia"),
    "data-bq-formacion": (30, 1, CARGA),
    "Reporte_CRM": (45, 1, REPORTE),
    "reportes-STC3.0": (60, 1, REPORTE),
    "cierre-formacion-stc3.0": (60, 1, "Marcar el cierre de formación y notificar a cada participante"),
    "envio-certificados-stc3.0": (90, 1, CORREOS + " con su certificado"),
    "correo-bienvenida-stc3.0": (30, 1, CORREOS),
    "vrd-fcs-stc3.0": (30, 1, "Actualizar el VRD en el consolidado FCS a mano"),
    "reporte-logs-sdde-formacion-stc3.0": (45, 1, REPORTE),
    # n8n · EFE
    "documentos-suba": (45, 1, CARPETAS),
    "actualizar-notas-eco": (45, 1, SIS),
    "asistencias-jae": (30, 1, SIS),
    "notas-modulares-jae": (30, 1, SIS),
    "consultas-colsubsidio": (30, 1, SIS),
    "actualizar-data-suba": (45, 1, SIS),
    "n8n-colsubsidio-carpetas-facturacion": (60, 1, CARPETAS),
    "n8n-suba-agente-minihas": (60, 1, "Revisar remisiones/autopostulaciones y responder una por una"),
    "n8n-suba-correos-integral-avanzado": (60, 1, CORREOS),
    "n8n-suba-correos-basico": (60, 1, CORREOS),
    "n8n-suba-correos-concatenados": (30, 1, CORREOS),
    "n8n-suba-carpetas-obligaciones": (60, 1, CARPETAS),
    "n8n-suba-data-looker": (20, 1, CARGA),
    "n8n-suba-certificados-satisfaccion": (90, 1, CORREOS + " con certificado y encuesta"),
    "n8n-suba-bonos": (45, 1, "Validar y asignar los bonos D1/Éxito y notificar"),
    "n8n-suba-comunicaciones-empresarial": (45, 1, CORREOS),
}


def main() -> None:
    cfg = tomllib.loads((RAIZ / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))
    ws = (gspread.service_account_from_dict(dict(cfg["gcp_service_account"]))
          .open_by_key(cfg["ops"]["sheet_id"]).worksheet("CATALOGO"))
    valores = ws.get_all_values()
    encabezado = valores[0]
    faltan = [c for c in COLUMNAS if c not in encabezado]
    aplicar = "--aplicar" in sys.argv
    if faltan:
        print(f"Columnas nuevas: {faltan}")
        if aplicar:
            if ws.col_count < len(encabezado) + len(faltan):
                ws.add_cols(len(encabezado) + len(faltan) - ws.col_count)
            inicio = gspread.utils.rowcol_to_a1(1, len(encabezado) + 1)
            ws.update(range_name=inicio, values=[faltan], value_input_option="RAW")
        encabezado = encabezado + faltan
    col = {c: encabezado.index(c) for c in encabezado}

    cambios, sin_propuesta = [], []
    for n_fila, v in enumerate(valores[1:], start=2):
        fila = dict(zip(encabezado, v + [""] * (len(encabezado) - len(v))))
        ident = fila.get("id", "").strip()
        if not ident:
            continue
        if ident not in PROPUESTA:
            if not fila.get("min_ahorro_ejecucion", "").strip():
                sin_propuesta.append(f"{ident} ({fila.get('nombre', '')})")
            continue
        minutos, tope, supuesto = PROPUESTA[ident]
        nuevos = {"min_ahorro_ejecucion": minutos, "tope_ejecuciones_dia": "" if tope is None else tope,
                  "ahorro_estado": "Estimado", "ahorro_supuesto": supuesto}
        escribir = {c: x for c, x in nuevos.items() if not str(fila.get(c, "")).strip() and x != ""}
        if not escribir:
            continue
        print(f"  {ident:<40} {minutos:>5} min  tope {tope or '–'}  · {supuesto[:60]}")
        for c, x in escribir.items():
            cambios.append({"range": gspread.utils.rowcol_to_a1(n_fila, col[c] + 1), "values": [[x]]})

    if sin_propuesta:
        print("\nSin propuesta (quedan 'sin estimar' hasta que alguien ponga los minutos):")
        for s in sin_propuesta:
            print("  -", s)
    if not cambios:
        print("\nNada que escribir.")
    elif aplicar:
        ws.batch_update(cambios, value_input_option="RAW")
        print(f"\n✔ {len(cambios)} celdas escritas en el CATALOGO. La página «Ahorro de tiempo» las toma en máx. 5 min.")
    else:
        print(f"\nSimulación: {len(cambios)} celdas por escribir. Corre con --aplicar.")


if __name__ == "__main__":
    main()
