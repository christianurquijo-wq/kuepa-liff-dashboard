"""
Reglas de negocio -- Ecolombia / Satisfacción (NPS).

A diferencia de Empleabilidad (donde cada regla se encontró por búsqueda
exhaustiva contra el pantallazo), aquí Christian compartió las fórmulas
OFICIALES con las que Looker agrupa las 17 preguntas de la encuesta
(`Satisfaccion_ECOPLUS_2026`, ya exclusiva de Ecolombia 2.0 -- ver
queries/ecolombia/satisfaccion.py):

    Evaluación docente     = promedio(pregunta_1..pregunta_4)
    Recursos académicos    = promedio(pregunta_5..pregunta_9)
    Plataforma             = promedio(pregunta_10..pregunta_13)
    Gestión Psicosocial    = promedio(pregunta_14..pregunta_15)
    Autoevaluación         = promedio(pregunta_16)
    NPS = %Promotores(9,10) - %Detractores(1..6) sobre
          COUNT(numero_de_documento_de_identidad) -- OJO: el 0 NO cuenta
          como detractor (la fórmula solo suma IF(pregunta_17=1..6,1,0),
          nunca =0). Con esto: Promotores=556, Detractores=63 (no 64),
          Total=814 -> (556-63)/814 = 60.57% -> redondea a 60.6%, EXACTO
          contra el pantallazo. Antes de tener esta fórmula se probó la
          definición clásica (detractor=0..6) y daba 60.44% -- no cuadraba;
          la diferencia era justo ese único encuestado con pregunta_17=0.

Validado contra el pantallazo "ECOLOMBIA+ 2026" con datos reales del
2026-09-18 (814 encuestas):

    Evaluación docente:  4.645 -> pantallazo 4.64  OK (exacto)
    Plataforma:          4.28  -> pantallazo 4.3   OK (redondeo)
    Gestión Psicosocial: 4.20  -> pantallazo 4.2   OK (exacto)
    Autoevaluación:      4.72  -> pantallazo 4.7   OK (redondeo)
    NPS:                 60.57%-> pantallazo 60.6% OK (exacto, ver arriba)
    Recursos académicos: 4.64  -> pantallazo 5     NO CUADRA

Recursos académicos queda como PENDIENTE DE ACLARAR CON EL CLIENTE -- la
fórmula oficial de Christian, aplicada tal cual sobre datos reales, da
4.64 (idéntico a Evaluación docente por coincidencia real de los datos,
no por bug -- ambos grupos de preguntas tienen el mismo denominador,
749/814, y promedios muy cercanos). No hay ninguna combinación de
columnas que reproduzca 5. Se muestra igual el 4.64 calculado (es el dato
defendible, con la fórmula ya validada al 100% en los otros 4
indicadores) con una nota visible en la página -- no se inventa un 5.

"Evaluación General" NO tiene fórmula oficial confirmada todavía -- se
usa el promedio simple de los 5 indicadores de arriba (4.50, redondea
igual que Promedio_Satisfaccion=4.48 de la vista Unificado_Satisfaccion,
que sí está pre-calculado pero mezclando los 5 proyectos de Kuepa). Si
Christian confirma la fórmula real, ajustar evaluacion_general() aquí.

"Activos" (263) NO se recalcula en esta página -- Christian confirmó que
es la MISMA tarjeta que en Pool de Empleabilidad (reutiliza
utils.ecolombia_empleabilidad_metrics.resumen_estados() sobre
TiempoEnPool sobre Google Sheets, no sobre estas tablas de BigQuery). La
página importa esa función directamente en vez de duplicar la lógica.

Las 3 gráficas que faltaban (barra agrupada por Grupo, ranking, barra por
Programa) se resolvieron leyendo el pantallazo directo -- ver
indicadores_por() abajo. Las 3 usan la MISMA fórmula oficial de arriba,
solo que agrupada por "grupo" o "programa_que_cursas" en vez de sobre
toda la tabla, y sin Autoevaluación (no aparece en la leyenda de esas
gráficas en el pantallazo, solo docente/recursos/plataforma/psicosocial).
Validado contra el pantallazo en el desglose por Programa (el único con
valores legibles en la imagen): T.L en Auxiliar de Mercadeo y Ventas =
4.54, T.L en Procesamiento y Digitación de Datos = 4.53, Técnico en
Hotelería y Turismo = 4.31. El orden exacto de las 20 barras por Grupo
en el pantallazo no se reconstruyó pixel a pixel (no afecta el valor,
solo el orden visual) -- si Christian necesita el mismo orden exacto de
Looker, avisar.

NPS -- dato importante encontrado al leer el donut del pantallazo: el
donut Promotor/Neutro/Detractor (68.3% / 23.8% / 7.9%) usa la definición
CLÁSICA de detractor (pregunta_17 = 0..6, incluye el 0), mientras que el
número "60.6%" de la tarjeta usa la fórmula oficial de Christian (1..6,
SIN el 0). Es decir: el propio Looker del cliente combina dos
definiciones de detractor distintas en la misma página (64 para el donut
vs 63 para el %). No es un error de este código -- nps_ecolombia() calcula
ambas por separado y cada una se usa donde corresponde, documentado en la
función para que no se "corrija" por accidente a futuro asumiendo que es
inconsistente.
"""
import pandas as pd

GRUPOS_PREGUNTAS = {
    "Evaluación docente": [1, 2, 3, 4],
    "Recursos académicos": [5, 6, 7, 8, 9],
    "Plataforma": [10, 11, 12, 13],
    "Gestión Psicosocial": [14, 15],
    "Autoevaluación": [16],
}

# Ver docstring del módulo -- excluye 0 de detractores a propósito, no
# cambiar sin volver a validar contra el pantallazo. Es la fórmula del
# NUMERO de NPS (la tarjeta "60.6%"), no la del donut (ver NPS_DETRACTOR_DONUT).
NPS_PROMOTOR = [9, 10]
NPS_DETRACTOR = [1, 2, 3, 4, 5, 6]

# Definición CLÁSICA (incluye el 0) -- es la que usa el DONUT del
# pantallazo, confirmada pixel a pixel: Detractor 7.9% = 64/814, no
# 63/814. Ver nota "NPS" en el docstring del módulo.
NPS_DETRACTOR_DONUT = [0, 1, 2, 3, 4, 5, 6]

# Los 4 indicadores que sí se desglosan por Grupo/Programa en el
# pantallazo -- Autoevaluación no aparece en esas 3 gráficas, solo como
# KPI general.
INDICADORES_DESGLOSABLES = {
    k: v for k, v in GRUPOS_PREGUNTAS.items() if k != "Autoevaluación"
}


def _a_numero(serie: pd.Series) -> pd.Series:
    """Igual criterio que en ecolombia_empleabilidad_metrics -- tolera
    coma decimal aunque en esta tabla las preguntas vengan como enteros
    simples ('5', '10'), por consistencia entre los dos toolchains."""
    return pd.to_numeric(
        serie.astype(str).str.strip().str.replace(",", ".", regex=False).replace({"": None}),
        errors="coerce",
    )


def _promedio_agrupado(df: pd.DataFrame, columnas: list) -> float:
    """SUM(col1)+SUM(col2)+.../COUNT(col1)+COUNT(col2)+... -- exactamente
    la fórmula de Christian. Equivale al promedio de TODOS los valores no
    nulos de las columnas juntas (no al promedio de los promedios), así
    que basta concatenar las series y sacar mean() una sola vez."""
    valores = pd.concat([_a_numero(df[c]) for c in columnas if c in df.columns])
    if valores.empty:
        return float("nan")
    return float(valores.mean())


def kpis_satisfaccion(df: pd.DataFrame) -> dict:
    """KPIs de evaluación (docente/recursos/plataforma/psicosocial/
    autoevaluación) + Evaluación General -- ver docstring del módulo para
    la fórmula de cada uno y qué SÍ y qué NO está confirmado."""
    resultado = {"encuestas": len(df)}
    for nombre, preguntas in GRUPOS_PREGUNTAS.items():
        columnas = [f"pregunta_{i}" for i in preguntas]
        resultado[nombre] = _promedio_agrupado(df, columnas)

    indicadores = [resultado[nombre] for nombre in GRUPOS_PREGUNTAS]
    indicadores_validos = [v for v in indicadores if pd.notna(v)]
    resultado["Evaluación General"] = (
        sum(indicadores_validos) / len(indicadores_validos) if indicadores_validos else float("nan")
    )
    return resultado


def nps_ecolombia(df: pd.DataFrame) -> dict:
    """NPS -- devuelve DOS desgloses distintos porque el pantallazo del
    cliente los usa distintos (ver nota "NPS" en el docstring del
    módulo):

    - pct / promotores / detractores / neutros: fórmula OFICIAL de
      Christian para la tarjeta "60.6%" -- Detractor = 1..6, el 0 no
      cuenta como detractor. Denominador = COUNT(numero_de_documento_de_identidad),
      no COUNT(pregunta_17) -- en la práctica da lo mismo porque
      pregunta_17 no tiene nulos en los datos actuales, pero se respeta
      la fórmula tal cual la dio Christian.
    - detractores_donut / neutros_donut: definición CLÁSICA (0..6) que
      usa el DONUT del pantallazo -- confirmado pixel a pixel (7.9% =
      64/814, no 63/814). promotores es el mismo en los dos casos."""
    if df.empty or "pregunta_17" not in df.columns:
        return {
            "promotores": 0, "neutros": 0, "detractores": 0,
            "neutros_donut": 0, "detractores_donut": 0,
            "total": 0, "pct": 0.0,
        }

    p17 = _a_numero(df["pregunta_17"])
    total = int(df["numero_de_documento_de_identidad"].notna().sum()) if "numero_de_documento_de_identidad" in df.columns else len(df)
    promotores = int(p17.isin(NPS_PROMOTOR).sum())
    detractores = int(p17.isin(NPS_DETRACTOR).sum())
    detractores_donut = int(p17.isin(NPS_DETRACTOR_DONUT).sum())
    neutros = total - promotores - detractores
    neutros_donut = total - promotores - detractores_donut
    pct = ((promotores - detractores) / total * 100) if total else 0.0

    return {
        "promotores": promotores,
        "neutros": neutros,
        "detractores": detractores,
        "neutros_donut": neutros_donut,
        "detractores_donut": detractores_donut,
        "total": total,
        "pct": pct,
    }


def indicadores_por(df: pd.DataFrame, columna: str) -> pd.DataFrame:
    """Los 4 indicadores desglosables (ver INDICADORES_DESGLOSABLES)
    calculados con la fórmula oficial de Christian, pero agrupados por
    `columna` ("grupo" o "programa_que_cursas") en vez de sobre toda la
    tabla -- misma fórmula, un GROUP BY más. Alimenta la barra agrupada
    por Grupo, el ranking, y la barra por Programa (ver docstring del
    módulo). "Evaluación General" aquí es el promedio simple de esos 4
    valores para esa fila -- igual criterio que evaluacion_general en
    kpis_satisfaccion(), sin fórmula oficial confirmada todavía.

    Validado contra el pantallazo en el desglose por programa_que_cursas
    (los únicos 3 valores legibles en la imagen): T.L en Auxiliar de
    Mercadeo y Ventas = 4.54, T.L en Procesamiento y Digitación de Datos
    = 4.53, Técnico en Hotelería y Turismo = 4.31."""
    columnas_vacias = [columna] + list(INDICADORES_DESGLOSABLES.keys()) + ["Evaluación General"]
    if df.empty or columna not in df.columns:
        return pd.DataFrame(columns=columnas_vacias)

    filas = []
    for valor, sub in df.groupby(columna):
        fila = {columna: valor}
        promedios_validos = []
        for nombre, preguntas in INDICADORES_DESGLOSABLES.items():
            columnas_preg = [f"pregunta_{i}" for i in preguntas]
            v = _promedio_agrupado(sub, columnas_preg)
            fila[nombre] = v
            if pd.notna(v):
                promedios_validos.append(v)
        fila["Evaluación General"] = (
            sum(promedios_validos) / len(promedios_validos) if promedios_validos else float("nan")
        )
        filas.append(fila)

    return pd.DataFrame(filas, columns=columnas_vacias)
