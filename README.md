# Kuepa Intelligence -- Dashboard (Streamlit)

Migración del dashboard académico (antes en n8n + HTML/Chart.js) a Python + Streamlit.

## Setup local

```bash
# 1. Crear entorno virtual (una sola vez)
python -m venv venv

# 2. Activarlo
#    Windows (PowerShell):
venv\Scripts\Activate.ps1
#    Windows (cmd):
venv\Scripts\activate.bat

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Copiar la plantilla de credenciales y llenarla con tus datos reales
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
#    (edita .streamlit/secrets.toml con los datos del Service Account)

# 5. Correr la app
streamlit run app.py
```

Debe abrir automáticamente `http://localhost:8501` en tu navegador.

## Estructura del proyecto

```
app.py                      # Portada / punto de entrada
pages/
  1_LIFF_Data.py             # Cada archivo aquí = una pestaña en el menú
utils/
  bigquery.py                # Conexión y cache a BigQuery (próximo paso)
queries/
  liff_data.py                # Queries SQL de la pestaña LIFF Data (próximo paso)
.streamlit/
  config.toml                 # Tema visual (colores Kuepa)
  secrets.toml.example        # Plantilla de credenciales (copiar -> secrets.toml)
  secrets.toml                # Credenciales reales -- NUNCA se sube a git
```
