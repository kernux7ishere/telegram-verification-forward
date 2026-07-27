import os
from flask import Flask, jsonify, render_template, request
from app.config import Config
from app.service import Service, get_service

def create_app(service: Service | None = None, start_bot: bool = True) -> Flask:
    flask_app = Flask(
        __name__,
        template_folder="../web/templates",
        static_folder="../web/static",
    )
    
    config = Config.from_env()
    flask_app.secret_key = config.flask_secret_key

    if service is None:
        service = get_service(config)

    if start_bot:
        service.start()

    @flask_app.get("/")
    def index():
        return render_template("index.html")

    @flask_app.get("/api/stats")
    def stats():
        return jsonify(service.stats.collect().to_dict())

    @flask_app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=3600"
        else:
            response.headers["Cache-Control"] = "no-store"
        return response

    return flask_app

import threading

def _delayed_start():
    if os.environ.get("RUN_BOT", "true").strip().lower() != "false":
        get_service(Config.from_env()).start()

app = create_app(start_bot=False)
threading.Thread(target=_delayed_start, daemon=True).start()

