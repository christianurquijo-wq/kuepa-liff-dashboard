"""
Crea la pestaña EFE_KPI_HISTORICO en el Google Sheet de operaciones ([ops] sheet_id) con los
52 registros mes x proyecto que estaban ESCRITOS A MANO dentro del código del dashboard de n8n
(nodo "Code in JavaScript8", HARDCODED_HISTORY). Desde ahí los lee la página
EFE General › KPIs históricos, y el equipo los actualiza cada mes sin tocar código.

    python scripts\\efe_kpi_historico_setup.py            (muestra lo que haría)
    python scripts\\efe_kpi_historico_setup.py --aplicar  (crea la pestaña y carga los datos)

Si la pestaña ya existe y tiene datos, NO la sobrescribe (para no borrar lo que hayan editado).
Columnas:
  mes (AAAA-MM) · proyecto · grupo (Further Education / Employability) · impactados (acumulado
  al corte) · nuevos (opcional: si se deja vacío se calcula como diferencia de impactados) ·
  retencion % · aprobacion % · nps · satisfaccion (1-5) · nota
Credenciales: [gcp_service_account] de .streamlit/secrets.toml (la misma del dashboard).
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import gspread

RAIZ = Path(__file__).resolve().parent.parent
PESTANA = "EFE_KPI_HISTORICO"
ENCABEZADO = ["mes", "proyecto", "grupo", "impactados", "nuevos", "retencion", "aprobacion", "nps",
              "satisfaccion", "nota"]

# (mes, proyecto, grupo, impactados, retencion, aprobacion, nps, satisfaccion) -- copiado tal cual de n8n
HISTORICO = [
    ('2026-01', 'Socios Talento Capital', 'Further Education', 534, 82.73, 81, None, None),
    ('2026-02', 'Socios Talento Capital', 'Further Education', 1022, 82.92, 82, None, None),
    ('2026-03', 'Socios Talento Capital', 'Further Education', 1638, 82.92, 82, None, None),
    ('2026-04', 'Socios Talento Capital', 'Further Education', 1638, None, None, None, None),
    ('2026-05', 'Socios Talento Capital', 'Further Education', 1638, None, None, None, None),
    ('2026-06', 'Socios Talento Capital', 'Further Education', 1638, None, None, None, None),
    ('2026-07', 'Socios Talento Capital', 'Further Education', 1638, None, None, None, None),
    ('2026-08', 'Socios Talento Capital', 'Further Education', 1638, None, None, None, None),
    ('2026-09', 'Socios Talento Capital', 'Further Education', 1638, None, None, None, None),
    ('2026-01', 'Colsubsidio 2026', 'Further Education', 280, 100, 58, 80, 4.80),
    ('2026-02', 'Colsubsidio 2026', 'Further Education', 1836, 99.87, 61, 83.25, 4.68),
    ('2026-03', 'Colsubsidio 2026', 'Further Education', 2452, 99.51, 80, 86.49, 4.68),
    ('2026-04', 'Colsubsidio 2026', 'Further Education', 2490, 99.51, 82, 85.00, 4.54),
    ('2026-05', 'Colsubsidio 2026', 'Further Education', 2490, None, None, None, None),
    ('2026-06', 'Colsubsidio 2026', 'Further Education', 2490, None, None, None, None),
    ('2026-07', 'Colsubsidio 2026', 'Further Education', 2490, None, None, None, None),
    ('2026-08', 'Colsubsidio 2026', 'Further Education', 2490, None, None, None, None),
    ('2026-09', 'Colsubsidio 2026', 'Further Education', 2490, None, None, None, None),
    ('2026-06', 'Colsubsidio 2.0 2026', 'Further Education', 53, 100, None, None, None),
    ('2026-07', 'Colsubsidio 2.0 2026', 'Further Education', 435, 98.65, 91.95, 81.68, 4.65),
    ('2026-08', 'Colsubsidio 2.0 2026', 'Further Education', 1377, 99.36, 91.72, 81.64, 4.74),
    ('2026-09', 'Colsubsidio 2.0 2026', 'Further Education', 2330, 99.44, 91.14, 81.33, 4.69),
    ('2026-01', 'Jóvenes a la E', 'Employability', 113, 93.08, 88, 67, 4.3),
    ('2026-02', 'Jóvenes a la E', 'Employability', 130, 92.30, 85, 68, 4.4),
    ('2026-03', 'Jóvenes a la E', 'Employability', 192, 92.45, 71.62, 60.00, 4.40),
    ('2026-04', 'Jóvenes a la E', 'Employability', 192, 95.75, 94.90, 86.79, 4.72),
    ('2026-05', 'Jóvenes a la E', 'Employability', 212, 94.81, 94.23, 40.00, 4.59),
    ('2026-06', 'Jóvenes a la E', 'Employability', 212, 93.87, 90.39, 70.59, 4.80),
    ('2026-07', 'Jóvenes a la E', 'Employability', 212, 95.75, 94.77, 75.00, 4.73),
    ('2026-08', 'Jóvenes a la E', 'Employability', 212, 93.40, 98.21, 53.33, 4.79),
    ('2026-09', 'Jóvenes a la E', 'Employability', 395, 96.46, 99.41, 60.13, 4.50),
    ('2026-02', 'Ecolombia 2.0', 'Employability', 26, 92.30, 85, None, None),
    ('2026-03', 'Ecolombia 2.0', 'Employability', 130, 94.38, 71.62, 66.66, 4.20),
    ('2026-04', 'Ecolombia 2.0', 'Employability', 151, 95.75, 94.90, 75.93, 4.53),
    ('2026-05', 'Ecolombia 2.0', 'Employability', 278, 94.24, 81.46, 85.71, 4.50),
    ('2026-06', 'Ecolombia 2.0', 'Employability', 299, 90.97, 89.87, 79.36, 4.49),
    ('2026-07', 'Ecolombia 2.0', 'Employability', 346, 95.95, 96.31, 87.18, 4.41),
    ('2026-08', 'Ecolombia 2.0', 'Employability', 359, 93.87, 94.31, 68.00, 4.35),
    ('2026-09', 'Ecolombia 2.0', 'Employability', 420, 93.57, 97.78, 87.50, 4.45),
    ('2026-03', 'Suba es Oportunidad', 'Further Education', 201, 100, 100, None, None),
    ('2026-04', 'Suba es Oportunidad', 'Further Education', 217, 99.16, 70.40, 61.33, 4.31),
    ('2026-05', 'Suba es Oportunidad', 'Further Education', 469, 97.74, 62.81, 78.26, 4.50),
    ('2026-06', 'Suba es Oportunidad', 'Further Education', 586, 97.76, 72.30, 89.47, 4.70),
    ('2026-07', 'Suba es Oportunidad', 'Further Education', 605, 98.07, 79.52, 91.30, 4.57),
    ('2026-08', 'Suba es Oportunidad', 'Further Education', 677, 97.82, 81.05, 75.00, 4.62),
    ('2026-09', 'Suba es Oportunidad', 'Further Education', 700, 97.90, 81.03, 75.31, 4.50),
    ('2026-07', 'Socios Talento Capital 3.0 Básico', 'Further Education', 283, None, None, None, None),
    ('2026-08', 'Socios Talento Capital 3.0 Básico', 'Further Education', 411, None, None, None, None),
    ('2026-09', 'Socios Talento Capital 3.0 Básico', 'Further Education', 1097, None, None, None, None),
    ('2026-07', 'Socios Talento Capital 3.0 Especializado', 'Further Education', 306, 97.06, 64.22, None, None),
    ('2026-08', 'Socios Talento Capital 3.0 Especializado', 'Further Education', 326, 87.11, 79.46, None, None),
    ('2026-09', 'Socios Talento Capital 3.0 Especializado', 'Further Education', 749, 81.68, 74.97, None, None),
]


def main() -> None:
    cfg = tomllib.loads((RAIZ / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))
    libro = gspread.service_account_from_dict(dict(cfg["gcp_service_account"])).open_by_key(cfg["ops"]["sheet_id"])
    filas = [ENCABEZADO] + [[m, p, g, imp, "", ret, apr, nps, sat, "Migrado de n8n (oct-2026)"]
                            for m, p, g, imp, ret, apr, nps, sat in HISTORICO]
    filas = [["" if v is None else v for v in f] for f in filas]
    existentes = [w.title for w in libro.worksheets()]
    if PESTANA in existentes:
        ws = libro.worksheet(PESTANA)
        if len(ws.get_all_values()) > 1:
            sys.exit(f"La pestaña {PESTANA} ya tiene datos: no la sobrescribo.")
    print(f"{len(filas) - 1} filas para {PESTANA} en «{libro.title}»")
    for f in filas[:4]:
        print("  ", f)
    if "--aplicar" not in sys.argv:
        print("Simulación. Corre con --aplicar para crearla.")
        return
    ws = libro.worksheet(PESTANA) if PESTANA in existentes else libro.add_worksheet(PESTANA, rows=500, cols=len(ENCABEZADO))
    ws.update(range_name="A1", values=filas, value_input_option="RAW")
    ws.freeze(rows=1)
    print(f"✔ Pestaña {PESTANA} lista. La página KPIs históricos la lee en máx. 10 min.")


if __name__ == "__main__":
    main()
