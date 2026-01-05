# mmonit_hub/__init__.py
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from flask import Flask, jsonify, redirect, render_template, request, url_for, session
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask_wtf.csrf import CSRFProtect

from config_loader import load_config
from auth_utils import (
    verify_password,
    verify_api_token,
    generate_passkey_registration_options,
    verify_passkey_registration,
    generate_passkey_authentication_options,
    verify_passkey_authentication,
    find_user_by_passkey,
)
from data_fetcher import query_mmonit_data
from webauthn.helpers import bytes_to_base64url, base64url_to_bytes

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

    # CSRF Protection
    csrf = CSRFProtect()
    csrf.init_app(app)

    # Exempt API routes from CSRF (will use Bearer token auth)
    csrf.exempt("api_data")

    @app.before_request
    def check_api_token_auth():
        """Check for Bearer token on API routes if not already authenticated"""
        if request.path.startswith("/api/") and not current_user.is_authenticated:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                username, user_cfg = verify_api_token(token, cfg)
                if username and user_cfg:
                    user = users_map.get(username)
                    if user:
                        login_user(user, remember=False)

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

    # --- WebAuthn/Passkey routes ---

    # Get user's passkeys from config
    def get_user_passkeys(username: str) -> list:
        for u in cfg.get("users", []):
            if u["username"] == username:
                return u.get("passkeys", [])
        return []

    # Get user_id bytes (deterministic based on username)
    def get_user_id(username: str) -> bytes:
        import hashlib
        return hashlib.sha256(username.encode()).digest()[:16]

    @app.post("/auth/passkey/login/begin")
    def passkey_login_begin():
        """Begin passkey authentication - returns challenge"""
        data = request.get_json() or {}
        username = data.get("username", "").strip()

        if not username:
            return jsonify({"error": "Username required"}), 400

        user_passkeys = get_user_passkeys(username)
        if not user_passkeys:
            return jsonify({"error": "No passkeys registered"}), 400

        options_json, challenge = generate_passkey_authentication_options(
            username, cfg, user_passkeys
        )
        session["webauthn_challenge"] = bytes_to_base64url(challenge)
        session["webauthn_username"] = username

        return options_json, 200, {"Content-Type": "application/json"}

    @app.post("/auth/passkey/login/complete")
    def passkey_login_complete():
        """Complete passkey authentication - verify response"""
        challenge_b64 = session.pop("webauthn_challenge", None)
        username = session.pop("webauthn_username", None)

        if not challenge_b64 or not username:
            return jsonify({"error": "No pending authentication"}), 400

        credential = request.get_json()
        if not credential:
            return jsonify({"error": "Missing credential"}), 400

        challenge = base64url_to_bytes(challenge_b64)
        credential_id = credential.get("id", "")

        # Find the stored credential
        stored_cred = None
        for cred in get_user_passkeys(username):
            if cred["id"] == credential_id:
                stored_cred = cred
                break

        if not stored_cred:
            return jsonify({"error": "Unknown credential"}), 400

        new_sign_count = verify_passkey_authentication(
            credential, challenge, stored_cred, cfg
        )

        if new_sign_count is None:
            return jsonify({"error": "Authentication failed"}), 401

        # Login the user
        user = users_map.get(username)
        if not user:
            return jsonify({"error": "User not found"}), 400

        login_user(user, remember=True)
        return jsonify({"success": True, "redirect": url_for("index")})

    @app.post("/auth/passkey/register/begin")
    @login_required
    def passkey_register_begin():
        """Begin passkey registration - returns challenge"""
        username = current_user.id
        user_id = get_user_id(username)
        existing = get_user_passkeys(username)

        options_json, challenge = generate_passkey_registration_options(
            username, user_id, cfg, existing
        )
        session["webauthn_reg_challenge"] = bytes_to_base64url(challenge)

        return options_json, 200, {"Content-Type": "application/json"}

    @app.post("/auth/passkey/register/complete")
    @login_required
    def passkey_register_complete():
        """Complete passkey registration - verify and store credential"""
        challenge_b64 = session.pop("webauthn_reg_challenge", None)

        if not challenge_b64:
            return jsonify({"error": "No pending registration"}), 400

        credential = request.get_json()
        if not credential:
            return jsonify({"error": "Missing credential"}), 400

        challenge = base64url_to_bytes(challenge_b64)
        cred_data = verify_passkey_registration(credential, challenge, cfg)

        if not cred_data:
            return jsonify({"error": "Registration failed"}), 400

        # Note: In production, you would save this to the config file
        # For now, return the credential data for manual addition
        cred_data["name"] = credential.get("name", "Passkey")
        cred_data["created"] = datetime.now(timezone.utc).isoformat()

        return jsonify({
            "success": True,
            "credential": cred_data,
            "message": "Add this to your config file under user's passkeys array"
        })

    @app.get("/settings")
    @login_required
    def settings():
        """User settings page for passkey management"""
        passkeys = get_user_passkeys(current_user.id)
        webauthn_enabled = "webauthn" in cfg
        return render_template(
            "settings.html",
            username=current_user.id,
            passkeys=passkeys,
            webauthn_enabled=webauthn_enabled,
        )

    # Exempt WebAuthn routes from CSRF (they use their own challenge mechanism)
    csrf.exempt("passkey_login_begin")
    csrf.exempt("passkey_login_complete")
    csrf.exempt("passkey_register_begin")
    csrf.exempt("passkey_register_complete")

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