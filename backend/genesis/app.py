#!/usr/bin/env python3
from flask import Flask
from routes.genesis import genesis_bp
from routes.actions import actions_bp
from routes.players import players_bp

def create_app():
    app = Flask(__name__)
    app.register_blueprint(genesis_bp, url_prefix="/api/genesis")
    app.register_blueprint(actions_bp, url_prefix="/api/genesis/actions")
    app.register_blueprint(players_bp, url_prefix="/api/genesis")
    return app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8787)
