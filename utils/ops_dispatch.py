"""
Disparo de automatizaciones desde el panel.

GitHub: API workflow_dispatch con un token fine-grained (Actions: Read and write
solo sobre los repos de automatizaciones). El request_id viaja como input y
aparece en el nombre de la ejecución (run-name), así el panel la encuentra.

n8n: POST al webhook del workflow con header X-OPS-TOKEN.
"""
from __future__ import annotations

import uuid

import requests
import streamlit as st

API = "https://api.github.com"


def nuevo_request_id() -> str:
    return uuid.uuid4().hex[:10]


def _gh_headers() -> dict:
    return {
        "Authorization": f"Bearer {st.secrets['ops']['github_token']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _owner() -> str:
    return st.secrets["ops"].get("github_owner", "christianurquijo-wq")


def disparar_github(item: dict, actor: str, request_id: str) -> tuple[bool, str]:
    workflow = item.get("workflow") or "ops_run_script.yml"
    script = str(item["script"])
    if script.startswith("lote:"):
        inputs = {"lote": script.split(":", 1)[1]}
    else:
        inputs = {"script": script, "cwd": item.get("cwd") or "script",
                  "timeout_min": str(int(item.get("timeout_min") or 60))}
    inputs.update({"origen": "boton", "actor": actor, "request_id": request_id})
    url = f"{API}/repos/{_owner()}/{item['repo']}/actions/workflows/{workflow}/dispatches"
    try:
        r = requests.post(url, headers=_gh_headers(), json={"ref": "main", "inputs": inputs}, timeout=20)
    except requests.RequestException as exc:
        return False, f"Sin conexión con GitHub: {exc}"
    if r.status_code in (200, 204):
        return True, "Solicitud enviada a GitHub Actions"
    if r.status_code == 404:
        return False, f"GitHub 404: no existe {workflow} en {item['repo']} (o el token no tiene acceso al repo)."
    return False, f"GitHub {r.status_code}: {r.text[:300]}"


def disparar_n8n(item: dict, actor: str, request_id: str) -> tuple[bool, str]:
    webhooks = dict(st.secrets["ops"].get("n8n_webhooks", {}))
    url = webhooks.get(item.get("webhook_key", ""))
    if not url:
        return False, f"Falta la URL del webhook '{item.get('webhook_key')}' en secrets [ops.n8n_webhooks]."
    try:
        r = requests.post(
            url,
            headers={"X-OPS-TOKEN": st.secrets["ops"].get("n8n_token", "")},
            json={"origen": "boton", "actor": actor, "request_id": request_id},
            timeout=30,
        )
    except requests.RequestException as exc:
        return False, f"Sin conexión con n8n: {exc}"
    if r.status_code < 300:
        return True, "Flujo de n8n iniciado"
    return False, f"n8n {r.status_code}: {r.text[:300]}"


@st.cache_data(ttl=15, show_spinner=False)
def runs_recientes(repo: str) -> list[dict]:
    """Últimas 20 ejecuciones del repo (para ver en curso y ubicar solicitudes)."""
    try:
        r = requests.get(f"{API}/repos/{_owner()}/{repo}/actions/runs",
                         headers=_gh_headers(), params={"per_page": 20}, timeout=15)
        r.raise_for_status()
    except requests.RequestException:
        return []
    return [
        {
            "repo": repo,
            "titulo": run.get("display_title", ""),
            "estado": run.get("status"),          # queued | in_progress | completed
            "conclusion": run.get("conclusion"),  # success | failure | cancelled | None
            "inicio": run.get("run_started_at") or run.get("created_at"),
            "url": run.get("html_url"),
            "evento": run.get("event"),
        }
        for run in r.json().get("workflow_runs", [])
    ]


def buscar_run(repo: str, request_id: str) -> dict | None:
    for run in runs_recientes(repo):
        if request_id and request_id in run["titulo"]:
            return run
    return None
