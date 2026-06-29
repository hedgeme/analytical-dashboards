import os
import sys
import time
import pathlib
import threading
import subprocess
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

from routes.data import data_bp
from routes.news import news_bp
from routes.analysis import analysis_bp

app = Flask(__name__)
CORS(app, origins=["*"])

app.register_blueprint(data_bp,     url_prefix="/dashboard/api")
app.register_blueprint(news_bp,     url_prefix="/dashboard/api")
app.register_blueprint(analysis_bp, url_prefix="/dashboard/api")


@app.route("/dashboard/health")
def health():
    return jsonify({"status": "ok", "version": "1.0"})


def _bot_supervisor():
    """Run telegram_bot.py as a subprocess with auto-restart on crash.
    Backs off if the bot exits too quickly (e.g. PID lock collision)."""
    script = str(pathlib.Path(__file__).parent / "telegram_bot.py")
    while True:
        print("[telegram] starting bot process…", flush=True)
        t_start = time.time()
        proc = subprocess.Popen([sys.executable, script], env=os.environ.copy())
        code = proc.wait()
        elapsed = time.time() - t_start
        if elapsed < 3:
            # Exited almost immediately — likely PID lock: another instance is running.
            print(f"[telegram] bot exited in {elapsed:.1f}s — another instance may be running; waiting 30s", flush=True)
            time.sleep(30)
        else:
            print(f"[telegram] bot exited (code {code}), restarting in 10s…", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        t = threading.Thread(target=_bot_supervisor, daemon=True, name="telegram-bot")
        t.start()

    port  = int(os.getenv("PORT", 5001))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
