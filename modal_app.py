"""Modal deployment for Recount: the web app, plus the Cala lookups that run in the background.

Deploy:  python3 -m modal deploy modal_app.py
Secrets: Modal secret `relay-secrets` (CALA_API_KEY, GEMINI_API_KEY, RELAY_DATABASE_URL, RELAY_DEMO_PASSCODE, COOKIE_KEY).
"""
from pathlib import Path

import modal

HERE = Path(__file__).parent
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi>=0.120", "starlette>=0.49.1", "psycopg[binary]==3.2.13", "requests>=2.32.4")
    .add_local_file(HERE / "llms.txt", remote_path="/root/llms.txt")
    .add_local_dir(HERE / "app", remote_path="/root/app")
)
app = modal.App("recount", image=image)
secrets = [modal.Secret.from_name("relay-secrets")]


@app.function(secrets=secrets, max_containers=1, scaledown_window=1200, timeout=600)
@modal.concurrent(max_inputs=50)
@modal.asgi_app(label="recount")
def web():
    import sys
    sys.path.insert(0, "/root/app")
    import main  # noqa: E402

    main.snap()  # load the snapshot from Aiven Postgres once per container
    return main.app
