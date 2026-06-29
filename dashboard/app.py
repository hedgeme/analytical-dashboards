import os
import threading
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

from routes.data import data_bp
from routes.news import news_bp
from routes.analysis import analysis_bp

app = Flask(__name__)
CORS(app, origins=["*"])  # Allow Claude artifacts and browser access

app.register_blueprint(data_bp,     url_prefix="/dashboard/api")
app.register_blueprint(news_bp,     url_prefix="/dashboard/api")
app.register_blueprint(analysis_bp, url_prefix="/dashboard/api")


@app.route("/dashboard/health")
def health():
    return jsonify({"status": "ok", "version": "1.0"})


def start_telegram_bot():
    """Start Telegram bot in background thread (optional — bot can also run as its own process)."""
    try:
        import telegram_bot
        telegram_bot.run()
    except Exception as e:
        print(f"[telegram] bot failed to start: {e}")


if __name__ == "__main__":
    # Start Telegram bot in a daemon thread so it dies when Flask exits.
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        t = threading.Thread(target=start_telegram_bot, daemon=True)
        t.start()

    port = int(os.getenv("PORT", 5001))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
