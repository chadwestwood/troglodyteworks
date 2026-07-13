#!/usr/bin/env python3
import os

from twe.app import create_app as create_twe_app
from routes.genesis import genesis_bp
from routes.actions import actions_bp
from routes.players import players_bp

def create_app():
    app = create_twe_app()
    app.register_blueprint(genesis_bp, url_prefix="/api/genesis")
    app.register_blueprint(actions_bp, url_prefix="/api/genesis/actions")
    app.register_blueprint(players_bp, url_prefix="/api/genesis")
    return app

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("TWE_BIND_HOST", "0.0.0.0")
    port = int(os.environ.get("TWE_BIND_PORT", "8787"))
    app.run(host=host, port=port)
