"""Modal deployment for Recount Signal, separate from the live 'recount' app (same image, same secrets).

Deploy:  python3 -m modal deploy modal_signal.py      (app and label 'recount-signal'; 'recount' is not touched)
Secrets: Modal secret `relay-secrets` (GEMINI_API_KEY, GEMINI_API_KEY_FALLBACK, RELAY_DATABASE_URL, COOKIE_KEY,
CALA_API_KEY). Signal files ship inside app/: signal_*.py, signal_extra.json (built by signal_extra_build.py),
signal_weights.json, signal_backtest.json and static/signal*.
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
app = modal.App("recount-signal", image=image)
secrets = [modal.Secret.from_name("relay-secrets")]


@app.function(secrets=secrets, max_containers=1, scaledown_window=1200, timeout=600)
@modal.concurrent(max_inputs=50)
@modal.asgi_app(label="recount-signal")
def web():
    import os
    import sys
    sys.path.insert(0, "/root/app")
    os.environ["SIGNAL_WARM"] = "off"  # warmed synchronously below instead of in a startup thread
    import main  # noqa: E402
    import signal_api  # noqa: E402

    main.snap()  # load the snapshot from Aiven Postgres once per container
    signal_api.warm()  # precompute scores, the default ranking and /api/signal/meta
    return main.app
