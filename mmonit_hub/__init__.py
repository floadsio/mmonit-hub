# mmonit_hub/__init__.py
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)

from config_loader import load_config
from auth_utils import verify_password
from data_fetcher import query_mmonit_data

LAST_FETCH_TIME = None  # populated on /api/data


def _resolve_config_path(cli_override: Optional[str] = None) -> Optional[str]:
    """
    Resolution order:
      1) cli_override if provided
      2) $MMONIT_HUB_CONFIG if exists
      3) ~/.mmonit-hub.conf if exists
      4) ./mmonit-hub.conf (repo root) if exists
    """
    if cli_override:
        return cli_override

    env_path = os.environ.get("MMONIT_HUB_CONFIG")
    if env_path and os.path.exists(env_path):
        return env_path

    home_path = os.path.expanduser("~/.mmonit-hub.conf")
    if os.path.exists(home_path):
        return home_path

    repo_path = os.path.join(os.path.dirname(__file__), "..", "mmonit-hub.conf")
    repo_path = os.path.abspath(repo_path)
    if os.path.exists(repo_path):
        return repo_path

    return None


# ---- Flask app factory & routes ----
class ConfigUser(UserMixin):
    def __init__(self, username: str, password_hash: str, tenants: List[str]):
        self.id = username
        self.password_hash = password_hash
        self.tenants = tenants


def create_app(config_path: Optional[str] = None) -> Flask:
    # silence InsecureRequestWarning when verify_ssl: false is used in config
    from urllib3 import disable_warnings
    from urllib3.exceptions import InsecureRequestWarning
    disable_warnings(InsecureRequestWarning)

    base_dir = Path(__file__).resolve().parent
    project_root = base_dir.parent
    templates_dir = project_root / "templates"
    static_dir = project_root / "static"

    app = Flask(__name__, template_folder=str(templates_dir), static_folder=str(static_dir))

    # resolve config path if not provided
    cfg_path = _resolve_config_path(config_path)
    cfg = load_config(cfg_path)  # exits with a friendly message if not found

    app.config["M_HUB_CONFIG"] = cfg
    app.config["SECRET_KEY"] = cfg.get("secret_key")

    ui = cfg.get("ui_thresholds", {})
    app.config["UI_THRESHOLDS"] = {
        "disk_warning_pct": int(ui.get("disk_warning_pct", 80)),
        "disk_error_pct": int(ui.get("disk_error_pct", 90)),
    }

    # Build in-memory users
    users_map: Dict[str, ConfigUser] = {
        u["username"]: ConfigUser(u["username"], u["password"], u.get("tenants", []))
        for u in cfg.get("users", [])
    }

    # Flask-Login
    login_manager = LoginManager()
    login_manager.login_view = "login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str) -> Optional[ConfigUser]:
        return users_map.get(user_id)

    # --- Auth routes ---
    @app.get("/login")
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("index"))
        return render_template("login.html", err=None)

    @app.post("/login")
    def login_post():
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = users_map.get(username)
        if not user or not verify_password(password, user.password_hash):
            return render_template("login.html", err="Invalid username or password"), 401
        login_user(user, remember=("remember" in request.form))
        return redirect(url_for("index"))

    @app.get("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    # --- App routes ---
    @app.get("/")
    @login_required
    def index():
        return render_template(
            "index.html",
            username=current_user.id,
            auto_refresh_seconds=int(cfg.get("auto_refresh_seconds", 0)),
            thresholds=app.config.get("UI_THRESHOLDS", {"disk_warning_pct": 80, "disk_error_pct": 90}),
        )

    @app.get("/api/data")
    @login_required
    def api_data():
        global LAST_FETCH_TIME
        allowed = current_user.tenants or ["*"]
        tenants = query_mmonit_data(cfg.get("instances", []), allowed)
        LAST_FETCH_TIME = datetime.now(timezone.utc)
        return jsonify({
            "username": current_user.id,
            "tenants": tenants,
            "last_fetch_time": int(LAST_FETCH_TIME.timestamp()),
            "refresh_interval": int(cfg.get("auto_refresh_seconds", 0)),
        })

    return app