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

## IQ -- cómo actualizar los datos

La pestaña IQ (`pages/2_IQ.py`) no se conecta directo a BigQuery: lee 2 hojas de
Google Sheets que alguien llena a mano. Para refrescar los números: (1) corre
`01_usuarios_recencia.sql` y `02_lecciones_wrapper.sql` en BigQuery, (2) pega
los resultados completos en las pestañas `IQ_usuarios` e `IQ_lecciones` del
Sheet (reemplazando todo el contenido anterior, no agregando filas al final),
y (3) espera hasta 1 hora a que expire el cache, o entra a la pestaña IQ y
apreta el botón **"🔄 Actualizar datos"** de la barra lateral para forzar la
relectura de inmediato. Si no hay `st.secrets["iq"]` configurado, la página
cae sola a datos de demostración (sintéticos) y lo avisa con un banner --
sirve para probar la app sin tocar las hojas reales.

## IQ -- Análisis dinámico / Detalle de consumo / Cobertura (cómo actualizar)

Estas páginas (`pages/iq/`) leen resúmenes ya agregados en
`data/iq/usage_hours/*.csv`, calculados a partir de la tabla de BigQuery
`active_usage_hours`. A diferencia de `pages/2_IQ.py`, esto NO se conecta
en vivo a Sheets ni a BigQuery -- no se pudo, la tabla es demasiado grande
para Sheets (1,19M+ filas, supera el límite de 10M celdas de un Sheet) y no
hay cuenta de servicio con acceso al proyecto de BigQuery donde vive.

**sept-2026, 2do rediseño:** Overview + Histórico se fusionaron en
**Análisis dinámico** (`pages/iq/1_Analisis_Dinamico.py`) porque Christian
necesitaba comparar por Mes/Trimestre/Semestre/Año, ver variación año
contra año (y contra el período inmediato anterior), y filtrar por
Rol/Grado/Región a la vez -- las 2 páginas viejas solo mostraban el mes
más reciente y una serie mensual sin esos filtros combinables. Los archivos
`pages/iq/1_Overview.py` y `pages/iq/2_Historico.py` quedaron en el repo
sin usar (ya no están en `app.py`, así que no aparecen en el menú ni se
ejecutan) -- se pueden borrar a mano cuando alguien tenga un minuto,
ningún archivo se sube/edita solo desde acá.

Hay dos familias de CSV en `data/iq/usage_hours/`:
- `mensual_alianza*.csv` (5 archivos): un solo grano (mensual) por una sola
  dimensión cada uno -- los sigue usando **Detalle de consumo** tal cual.
- `detalle_<grano>.csv` / `totales_<grano>.csv` (grano = mensual, trimestral,
  semestral, anual -- 8 archivos): los usa **Análisis dinámico**. Los
  `totales_*` dan el número exacto de usuarios únicos por Alianza y período
  (sin desglosar Rol/Grado/Región); los `detalle_*` desglosan por esas 3
  dimensiones para que se puedan filtrar/combinar -- con una limitación
  documentada en el docstring de `utils/iq_usage_hours.py`: si se
  seleccionan **varios valores de la misma dimensión a la vez** (ej. 2
  grados), una persona que aparece en ambos en el mismo período se cuenta
  2 veces. Es inherente a trabajar con agregados estáticos y no con la
  data cruda en vivo; la propia página avisa cuando aplica.

Para refrescar estos 15 archivos (proceso manual, no hay botón "Actualizar" acá):

1. Christian exporta la tabla desde la consola de BigQuery con su propio
   usuario (`bq` CLI), partida en varios Excel/CSV para no pasar el límite
   de exportación -- ver el historial de la conversación con Claude de
   sept-2026 para las consultas SQL exactas usadas.
2. Se le pasan esos archivos a Claude (o se repite el script de agregación
   que generó los CSV actuales), que los limpia (dedup por `_id`, fechas
   mixtas, normaliza nombres de Regional Educativa) y agrega en pandas a
   los 4 grados de detalle -- NUNCA se sube la data cruda al repo, solo
   los agregados chicos.
3. Se reemplazan los 15 archivos de `data/iq/usage_hours/` y se hace
   commit. No hay cache que limpiar del lado de la app -- son archivos
   estáticos, el cache de 1h (`@st.cache_data`) solo afecta cuánto tarda
   en notarse un redeploy.

**Cobertura conocida (sept-2026):** hay 2 huecos confirmados donde ningún
archivo exportado tiene datos -- 23 dic 2021 a 3 ene 2022, y 1-14 jun 2023.
Ver la página **Cobertura** dentro de la app para el detalle completo y
cómo se detectaron (no es "días sin actividad", es "ningún archivo cubre
ese rango de fechas" -- son cosas distintas, ver el docstring de
`pages/iq/4_Cobertura.py`). Los datos ahora llegan hasta el 22-sep-2026
(antes el corte era anterior).
