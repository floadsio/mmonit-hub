import base64, hashlib, hmac, json, secrets, sys
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for
import requests

from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)

CONFIG_FILE = "mmonit-hub.conf"
AUTO_REFRESH_INTERVAL = 30
LAST_FETCH_TIME = None


# ---- Auth helpers (password hashing stays the same) ----
def hash_password(password: str, salt: str | None = None) -> str:
    if salt is None:
        salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}${pwd_hash.hex()}"

def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, _ = password_hash.split("$", 1)
        return hmac.compare_digest(hash_password(password, salt), password_hash)
    except Exception:
        return False


# ---- Config ----
def load_config(path: str):
    global AUTO_REFRESH_INTERVAL
    try:
        with open(path, "r") as f:
            cfg = json.load(f)
        AUTO_REFRESH_INTERVAL = cfg.get("auto_refresh_seconds", AUTO_REFRESH_INTERVAL)
        if cfg.get("users"):
            for u in cfg["users"]:
                if not {"username", "password", "tenants"} <= set(u):
                    print("Warning: each user must have username/password/tenants")
        return cfg
    except FileNotFoundError:
        example = {
            "port": 8080,
            "secret_key": "change-me",
            "auto_refresh_seconds": 30,
            "users": [{"username": "admin", "password": "hashed-password", "tenants": ["*"]}],
            "instances": [{
                "name": "tenant1",
                "url": "https://mmonit1.example.com:8080",
                "username": "admin",
                "password": "password1"
            }]
        }
        print(f"Error: Config file '{path}' not found!\n")
        print("Create a config file with this format:")
        print(json.dumps(example, indent=2))
        print("\nNote: Use --hash-password to generate password hashes")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config: {e}")
        sys.exit(1)


# ---- Data collector (unchanged) ----
def _mark_host_na(host: dict):
    host["filesystems"] = []
    host["issues"] = []
    host["service_count"] = 0
    host["os_name"] = "OS N/A"
    host["os_release"] = ""
    host["services_detail"] = []
    host["service_names"] = []

def query_mmonit_data(instances, allowed_tenants=None):
    result = []
    for instance in instances:
        name = instance["name"]
        if allowed_tenants and "*" not in allowed_tenants and name not in allowed_tenants:
            continue

        url = instance["url"]
        username = instance["username"]
        password = instance["password"]
        verify_ssl = instance.get("verify_ssl", False)

        try:
            s = requests.Session()
            s.get(f"{url}/index.csp", timeout=10, verify=verify_ssl)
            r = s.post(
                f"{url}/z_security_check",
                data={"z_username": username, "z_password": password, "z_csrf_protection": "off"},
                timeout=10,
                verify=verify_ssl,
            )
            if r.status_code != 200:
                result.append({"tenant": name, "url": url, "error": f"Login failed: HTTP {r.status_code}", "hosts": []})
                continue

            api_version = instance.get("api_version", "2")
            rl = s.get(
                f"{url}/api/{api_version}/status/hosts/list",
                params={"results": 1000},
                timeout=10,
                verify=verify_ssl,
            )
            if rl.status_code != 200:
                result.append({"tenant": name, "url": url, "error": f"API error: HTTP {rl.status_code}", "hosts": []})
                continue

            hosts = rl.json().get("records", [])
            for host in hosts:
                try:
                    rd = s.get(
                        f"{url}/api/{api_version}/status/hosts/get",
                        params={"id": host["id"]},
                        timeout=10,
                        verify=verify_ssl,
                    )
                    if rd.status_code != 200:
                        _mark_host_na(host)
                        continue

                    host_rec = rd.json().get("records", {}).get("host", {})
                    platform = host_rec.get("platform", {})
                    host["os_name"] = platform.get("name", "OS N/A")
                    host["os_release"] = platform.get("release", "")

                    filesystems, issues = [], []
                    services = host_rec.get("services", [])
                    host["service_count"] = len(services)

                    services_detail, service_names = [], []
                    for svc in services:
                        if svc.get("led") in [0, 1]:
                            issues.append(
                                {
                                    "name": svc.get("name", "Unknown"),
                                    "type": svc.get("type", "Unknown"),
                                    "status": svc.get("status", "Unknown"),
                                    "led": svc.get("led"),
                                }
                            )
                        if svc.get("type") == "Filesystem":
                            fs_info = {"name": svc.get("name", "Unknown"), "usage_percent": None, "usage_mb": None, "total_mb": None}
                            for stat in svc.get("statistics", []):
                                t = stat.get("type")
                                if t == 18:
                                    fs_info["usage_percent"] = stat.get("value")
                                elif t == 19:
                                    fs_info["usage_mb"] = stat.get("value")
                                elif t == 20:
                                    fs_info["total_mb"] = stat.get("value")
                            if fs_info["usage_percent"] is not None:
                                filesystems.append(fs_info)

                        services_detail.append(
                            {
                                "name": svc.get("name", "Unknown"),
                                "type": svc.get("type", "Unknown"),
                                "status": svc.get("status", "Unknown"),
                                "led": svc.get("led", 2),
                            }
                        )
                        if svc.get("name"):
                            service_names.append(svc["name"])

                    host["filesystems"] = filesystems
                    host["issues"] = issues
                    host["services_detail"] = services_detail
                    host["service_names"] = service_names
                except Exception:
                    _mark_host_na(host)

            result.append({"tenant": name, "url": url, "hosts": hosts})
        except requests.exceptions.Timeout:
            result.append({"tenant": name, "url": url, "error": "Connection timeout", "hosts": []})
        except requests.exceptions.ConnectionError:
            result.append({"tenant": name, "url": url, "error": "Connection failed", "hosts": []})
        except Exception as e:
            result.append({"tenant": name, "url": url, "error": str(e), "hosts": []})
    return result


# ---- Flask app factory & routes (Flask-Login) ----
class ConfigUser(UserMixin):
    def __init__(self, username: str, password_hash: str, tenants: list[str]):
        self.id = username
        self.password_hash = password_hash
        self.tenants = tenants

def create_app(config_path: str = CONFIG_FILE):
    from urllib3 import disable_warnings
    from urllib3.exceptions import InsecureRequestWarning
    disable_warnings(InsecureRequestWarning)

    # Ensure Flask sees your top-level templates/ and static/
    base_dir = Path(__file__).resolve().parent
    project_root = base_dir.parent
    templates_dir = project_root / "templates"
    static_dir = project_root / "static"

    app = Flask(__name__, template_folder=str(templates_dir), static_folder=str(static_dir))
    cfg = load_config(config_path)
    app.config["M_HUB_CONFIG"] = cfg
    app.config["SECRET_KEY"] = cfg.get("secret_key") or secrets.token_hex(32)  # prefer config
    ui = cfg.get("ui_thresholds", {})
    app.config["UI_THRESHOLDS"] = {
        "disk_warning_pct": int(ui.get("disk_warning_pct", 80)),
        "disk_error_pct": int(ui.get("disk_error_pct", 90)),
    }

    # Build in-memory user map
    users_map: dict[str, ConfigUser] = {}
    for u in cfg.get("users", []):
        users_map[u["username"]] = ConfigUser(u["username"], u["password"], u.get("tenants", []))

    # Flask-Login setup
    login_manager = LoginManager()
    login_manager.login_view = "login"  # redirect here when not logged in
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
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
        payload = {
            "username": current_user.id,
            "tenants": tenants,
            "last_fetch_time": int(LAST_FETCH_TIME.timestamp()),
            "refresh_interval": int(cfg.get("auto_refresh_seconds", 0)),
        }
        return jsonify(payload)

    return app