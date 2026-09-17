"""
Query -- Ecolombia / CONVOCATORIA -- embudo completo de candidatos.

Tabla distinta a ECOPLUS_V2_2026 (overview.py): CONVOCATORIA es el embudo
completo de candidatos (preinscripción -> entrevista -> matrícula), no
solo los ya matriculados. Confirmado por esquema: 2704 filas, todas con
proyecto == "Ecolombia 2.0" y cohorte == "C1" (hoy solo existe esa
cohorte en esta tabla -- si Ecolombia abre una cohorte C2, esta tabla
debería empezar a traer más de un valor distinto en `cohorte`).

Se traen también cohorte/programa/ciudad/grupo/sexo para poder aplicarle
los mismos filtros de la página que ya se le aplican a la data de
ECOPLUS_V2_2026 -- ambas tablas comparten esas 5 columnas.

Columnas agregadas el 2026-09-17 para la página Selección y Matrícula
(embudo completo + Aliado-Referido + históricos) -- ver
utils/ecolombia_seleccion_metrics.py para la lógica de negocio de cada
una, confirmada número por número contra el pantallazo de Looker:

    estado_preinscripcion    Cumple requisitos / Descartado
    estado_final_fase_i      Matriculado / Retiro / Pendiente Contrato /
                              En proceso de matrícula / Pendiente
                              Documentos / No Contactabilidad / ...
    aliado__referido         canal de adquisición (tabla "Aliado-Referido")
    adnetwork                filtro "Adnetwork" del pantallazo
    fecha_de_matricula        insumo del histórico acumulado de matrículas
    fecha_de_preinscripcion   insumo del histórico de preinscritos por día
"""

TABLA = "`sustained-edge-465417-m3.EFE_2026.ECOPLUS_2026_CONVOCATORIA`"

QUERY = f"""
SELECT
  cohorte,
  programa,
  ciudad,
  grupo,
  sexo,
  resultado_entrevista,
  estado_de_matricula,
  estado_preinscripcion,
  estado_final_fase_i,
  aliado__referido,
  adnetwork,
  fecha_de_matricula,
  fecha_de_preinscripcion
FROM {TABLA}
"""


def get_convocatoria_query() -> str:
    return QUERY
