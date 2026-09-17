"""
Componentes visuales compartidos entre páginas/proyectos.

Todo lo que hay aquí es SOLO presentación (tarjetas de KPI, badges, tema
oscuro para Plotly, CSS de la página) -- ningún cálculo de negocio vive en
este archivo. Se extrajo de pages/1_LIFF_Data.py cuando Ecolombia (Overview)
empezó a necesitar exactamente los mismos componentes; a partir de ahora
CUALQUIER página nueva (de cualquier proyecto) debe importar de aquí en vez
de duplicar estas funciones localmente.

Si cambias un color o el estilo de una tarjeta, el cambio aplica a TODAS las
páginas que usan este módulo -- no es como Master Library de Apps Script
(no hay clientes licenciados de por medio), pero sigue siendo un cambio
transversal: revisa LIFF Data y Ecolombia antes de dar por bueno un ajuste
aquí.
"""
import streamlit as st

# -- Paleta (coherente con .streamlit/config.toml) --------------------------
NARANJA = "#FD531E"  # marca Kuepa
AZUL = "#29B6F6"  # dato secundario / "grupo B"
VERDE = "#2ECC71"  # positivo
AMARILLO = "#F5B942"  # en curso / advertencia leve
ROJO = "#E74C3C"  # negativo
GRIS = "#8C8C8C"  # neutral / pendiente

CHART_HEIGHT = 320

PAGE_CSS = """
<style>
  .block-container { padding-top: 2.2rem; }
  h3 { margin-top: 0.4rem; margin-bottom: 0.8rem; }
</style>
"""


def inject_css() -> None:
    """Llama esto una vez al inicio de cada página."""
    st.markdown(PAGE_CSS, unsafe_allow_html=True)


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    """'#FD531E' + 0.35 -> 'rgba(253, 83, 30, 0.35)' -- para los links de
    un Sankey (necesitan transparencia; los nodos usan el hex tal cual)."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


def dark(fig, height: int = CHART_HEIGHT):
    """Tema oscuro de Kuepa + altura uniforme -- Streamlit no aplica el
    tema del .streamlit/config.toml a las figuras de Plotly solas, hay
    que pedirlo explícitamente en cada una."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#FAFAFA",
        height=height,
        margin=dict(t=45, b=10, l=10, r=10),
        legend_title_text="",
    )
    return fig


def badge(texto: str, color: str = NARANJA) -> str:
    return (
        f"<span style='background:{color}; color:white; padding:5px 14px; "
        f"border-radius:12px; font-weight:600; font-size:0.78rem; "
        f"white-space:nowrap;'>{texto}</span>"
    )


def kpi_card(label: str, value: str, color: str = NARANJA, help_text: str = "") -> str:
    ayuda_html = (
        f"<div style='font-size:0.68rem; color:#9A9A9A; margin-top:4px; "
        f"line-height:1.2;'>{help_text}</div>"
        if help_text
        else ""
    )
    return f"""
<div style="background:#1A1A1A; border-left:4px solid {color}; border-radius:8px;
            padding:14px 16px; min-height:92px;">
  <div style="font-size:0.7rem; letter-spacing:0.04em; color:#AAAAAA;
              text-transform:uppercase;">{label}</div>
  <div style="font-size:1.85rem; font-weight:700; color:{color};
              margin-top:6px; line-height:1;">{value}</div>
  {ayuda_html}
</div>
"""


def kpi_row(cards: list) -> None:
    """cards: lista de tuplas (label, value, color, help_text)."""
    cols = st.columns(len(cards))
    for col, (label, value, color, help_text) in zip(cols, cards):
        with col:
            st.markdown(kpi_card(label, value, color, help_text), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Clic-para-filtrar: un clic en una barra/porción de pastel hace lo mismo
# que elegir esa opción en el selectbox de filtro correspondiente.
#
# Mecanismo elegido a propósito (confirmado con Christian, sept-2026):
# el clic actualiza el MISMO selectbox que ya existe -- no hay un sistema
# de cross-filter paralelo. Esto reutiliza toda la lógica de filtrado ya
# validada; lo único nuevo es "¿qué session_state[key] hay que tocar?".
#
# Usa on_select=callback (no on_select="rerun" + manejo manual) porque
# Streamlit prohíbe escribir session_state[key] de un widget DESPUÉS de
# que ese widget ya se instanció en el mismo run -- el selectbox de
# arriba ya corrió para cuando se procesa el clic de una gráfica más
# abajo. Un callback corre en su propio momento (como on_change), así que
# sí puede escribir el session_state de OTRO widget sin choque; Streamlit
# hace el rerun automáticamente después.
#
# Requiere que la gráfica se haya creado con custom_data=["<columna>"] --
# así el valor clickeado siempre llega en punto["customdata"][0], sin
# depender de si Streamlit lo reporta en "x", "y" o "label" (varía entre
# barra y pastel, y hay bugs reportados en Streamlit justo para ese caso).
# ---------------------------------------------------------------------------
def click_to_filter(chart_key: str, filter_key: str):
    """
    Devuelve el callback para pasar a on_select= de un st.plotly_chart:

        fig = px.bar(..., custom_data=["programa"])
        st.plotly_chart(
            fig,
            key="eco_chart_programa",
            on_select=click_to_filter("eco_chart_programa", "eco_programa_sel"),
            selection_mode="points",
        )

    `chart_key` debe ser el mismo `key=` de ese st.plotly_chart.
    `filter_key` debe ser el `key=` del selectbox que se quiere actualizar.
    """

    def _callback() -> None:
        event = st.session_state.get(chart_key)
        if not event:
            return
        selection = event["selection"] if isinstance(event, dict) else event.selection
        if not selection:
            return
        points = selection["points"] if isinstance(selection, dict) else selection.points
        if not points:
            return
        punto = points[0]
        customdata = punto["customdata"] if isinstance(punto, dict) else punto.customdata
        if customdata:
            st.session_state[filter_key] = customdata[0]

    return _callback
