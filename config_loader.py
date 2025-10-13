# config_loader.py
import json, sys, os
from pathlib import Path

AUTO_REFRESH_INTERVAL = 30

# Resolution order (highest to lowest):
# 1) CLI arg passed by app.py (or your caller)
# 2) Env var MMONIT_HUB_CONFIG
# 3) ~/.mmonit-hub.conf
# 4) ./mmonit-hub.conf  (repo root)

def _first_existing(paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None

def load_config(cli_path: str | None = None):
    env_path  = os.environ.get("MMONIT_HUB_CONFIG")
    home_path = str(Path.home() / ".mmonit-hub.conf")
    repo_path = os.path.join(os.path.dirname(__file__), "mmonit-hub.conf")

    final_path = _first_existing([cli_path, env_path, home_path, repo_path])
    if not final_path:
        print("Error: Config file 'mmonit-hub.conf' not found!", file=sys.stderr)
        print("\nCreate a config file with this format:")
        print(json.dumps({
            "port": 8082,
            "auto_refresh_seconds": 30,
            "users": [
                {"username": "admin", "password": "hashed-password", "tenants": ["*"]}
            ],
            "instances": [
                {
                    "name": "tenant1",
                    "url": "https://mmonit1.example.com:8080",
                    "username": "admin",
                    "password": "password1",
                    "verify_ssl": False,
                    "api_version": "2"
                }
            ]
        }, indent=2))
        print("\nNote: Use --hash-password to generate password hashes")
        sys.exit(1)

    with open(final_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    global AUTO_REFRESH_INTERVAL
    AUTO_REFRESH_INTERVAL = cfg.get("auto_refresh_seconds", AUTO_REFRESH_INTERVAL)

    # Basic validation
    for user in cfg.get("users", []):
        if not all(k in user for k in ("username", "password", "tenants")):
            print("Warning: each user must have username, password, tenants")

    cfg["_config_source"] = final_path
    return cfg

def get_auto_refresh_interval():
    return AUTO_REFRESH_INTERVAL