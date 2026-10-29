"""Piezas de interfaz compartidas por las páginas de EFE General."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.ops_auth import requiere_login
from utils.ui import AMARILLO, AZUL, GRIS, NARANJA, ROJO, VERDE, dark, inject_css

TODOS = "Todos"
PALETA = [NARANJA, AZUL, VERDE, AMARILLO, "#A569BD", ROJO, GRIS, "#48C9B0", "#F1948A", "#5DADE2"]


def inicio(titulo: str, subtitulo: str) -> str:
    """CSS + login (misma lista del Panel de control) + título. Devuelve el correo."""
    inject_css()
    correo = requiere_login(
        titulo="EFE General",
        mensaje="Esta sección tiene datos personales de los participantes. "
                "Inicia sesión con tu cuenta de Google de Kuepa.",
    )
    st.title(titulo)
    st.caption(subtitulo)
    return correo


def filtro(df: pd.DataFrame, columna: str, etiqueta: str, key: str, contenedor=st) -> str:
    opciones = [TODOS] + sorted(df[columna].dropna().astype(str).unique())
    return contenedor.selectbox(etiqueta, opciones, key=key)


def aplicar(df: pd.DataFrame, columna: str, valor: str) -> pd.DataFrame:
    return df if valor == TODOS else df[df[columna].astype(str) == valor]


def barras(datos: pd.DataFrame, x: str, y: str, titulo: str, color: str | None = None, horizontal: bool = False,
           texto: str | None = None, altura: int = 340, orden: list | None = None, **kw):
    if datos.empty:
        st.info(f"{titulo}: sin datos para este filtro.")
        return
    args = dict(x=y, y=x, orientation="h") if horizontal else dict(x=x, y=y)
    fig = px.bar(datos, title=titulo, color=color, text=texto or y,
                 color_discrete_sequence=PALETA if color else [NARANJA],
                 category_orders={x: orden} if orden else None, **args, **kw)
    fig.update_traces(textposition="outside" if not color else "inside", cliponaxis=False)
    if horizontal:
        fig.update_layout(yaxis={"categoryorder": "total ascending"} if not orden else {})
    st.plotly_chart(dark(fig, altura), use_container_width=True)


def dona(conteo: pd.Series, titulo: str, altura: int = 320, colores: dict | None = None):
    conteo = conteo[conteo > 0]
    if conteo.empty:
        st.info(f"{titulo}: sin datos para este filtro.")
        return
    fig = px.pie(names=conteo.index.astype(str), values=conteo.values, hole=0.55, title=titulo,
                 color=conteo.index.astype(str), color_discrete_map=colores or {},
                 color_discrete_sequence=PALETA)
    fig.update_traces(textinfo="percent+value")
    st.plotly_chart(dark(fig, altura), use_container_width=True)


def conteo(df: pd.DataFrame, columna: str, unidad: str = "Documento") -> pd.DataFrame:
    """Personas distintas por valor de la columna (los vacíos quedan como 'Sin dato')."""
    col = df[columna].astype("object")  # admite categóricas (rango de edad)
    x = df.assign(**{columna: col.where(col.notna(), "Sin dato").astype(str)})
    return (x.groupby(columna)[unidad].nunique().rename("Personas").reset_index()
            .sort_values("Personas", ascending=False))


def eje_periodo(fig):
    """Las etiquetas de periodo ('2026-09', 'Sem 06/10/2026') se muestran tal cual, en orden,
    sin que Plotly las convierta a fechas en inglés ('Sep 2026')."""
    fig.update_xaxes(type="category", title=None)
    return fig
