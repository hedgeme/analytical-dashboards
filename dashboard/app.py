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
    """Run telegram_bot.py as a subprocess with auto-restart on crash."""
    script = str(pathlib.Path(__file__).parent / "telegram_bot.py")
    while True:
        print("[telegram] starting bot process…", flush=True)
        proc = subprocess.Popen([sys.executable, script], env=os.environ.copy())
        code = proc.wait()
        print(f"[telegram] bot exited (code {code}), restarting in 5s…", flush=True)
        time.sleep(5)


if __name__ == "__main__":
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        t = threading.Thread(target=_bot_supervisor, daemon=True, name="telegram-bot")
        t.start()

    port  = int(os.getenv("PORT", 5001))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
