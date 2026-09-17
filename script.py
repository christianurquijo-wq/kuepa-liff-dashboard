
import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

creds = service_account.Credentials.from_service_account_file(
    "service_account.json",
    scopes=["https://www.googleapis.com/auth/cloud-platform"],
)
client = bigquery.Client(credentials=creds, project=creds.project_id)

query = """
SELECT resultado_entrevista, estado_final_fase_i, COUNT(*) AS n
FROM `sustained-edge-465417-m3.EFE_2026.ECOPLUS_2026_CONVOCATORIA`
WHERE resultado_entrevista IN ('Pasa', 'Repechaje', 'No pasa')
GROUP BY 1, 2
ORDER BY 1, n DESC
"""
print(client.query(query).to_dataframe().to_string())