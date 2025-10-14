#!/usr/bin/env python3
import os
import sys
import argparse
import getpass
from typing import Optional

from mmonit_hub import create_app          # expects a path string
from config_loader import load_config
from auth_utils import hash_password


def _resolve_config_path(cli_override: Optional[str] = None) -> Optional[str]:
    """
    Resolution order:
      1) CLI override (only when running as __main__)
      2) Env var MMONIT_HUB_CONFIG
      3) ~/.mmonit-hub.conf
      4) ./mmonit-hub.conf (repo root)
    Returns the first existing path or None.
    """
    if cli_override:
        return cli_override

    env_path = os.environ.get("MMONIT_HUB_CONFIG")
    if env_path and os.path.exists(env_path):
        return env_path

    home_path = os.path.expanduser("~/.mmonit-hub.conf")
    if os.path.exists(home_path):
        return home_path

    repo_path = os.path.join(os.path.dirname(__file__), "mmonit-hub.conf")
    if os.path.exists(repo_path):
        return repo_path

    return None


# ------------------------------------------------------------------------------------
# Module-level app for gunicorn / `flask run`
# (must pass a PATH to create_app, not a dict)
# ------------------------------------------------------------------------------------
_cfg_path_for_import = _resolve_config_path(None)
cfg_for_import = load_config(_cfg_path_for_import)  # exits with sample if not found
app = create_app(_cfg_path_for_import)

# ------------------------------------------------------------------------------------
# CLI entrypoint (only used with `python app.py ...`)
# ------------------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="M/Monit Hub (Flask) Launcher")
    parser.add_argument("--config", help="Path to configuration file (overrides env/home/repo)")
    parser.add_argument("--hash-password", action="store_true", help="Generate password hash and exit")
    args = parser.parse_args()

    if args.hash_password:
        pw1 = getpass.getpass("Enter password to hash: ")
        pw2 = getpass.getpass("Confirm password: ")
        if pw1 != pw2:
            print("Error: Passwords do not match.")
            sys.exit(1)
        print("\nHashed password:")
        print(hash_password(pw1))
        sys.exit(0)

    # If a CLI --config is provided, resolve + run with that
    if args.config:
        cfg = load_config(args.config)  # validate & for logging
        port = int(cfg.get("port", 8080))

        print("M/Monit Hub (Flask) starting…")
        print(f"✅ Config: {args.config}")
        print(f"Monitoring {len(cfg.get('instances', []))} tenant(s)")
        users = cfg.get("users", [])
        print(
            f"🔐 Login: Flask-Login enabled ({len(users)} user(s))"
            if users
            else "⚠️  Login: Disabled (anonymous access)"
        )
        print(f"📊 Dashboard: http://localhost:{port}\n")

        local_app = create_app(args.config)
        local_app.run(host="0.0.0.0", port=port)
        return

    # Otherwise use the module-level config (env/home/repo)
    port = int(cfg_for_import.get("port", 8080))
    print("M/Monit Hub (Flask) starting…")
    print(f"✅ Config: {_cfg_path_for_import}")
    print(f"Monitoring {len(cfg_for_import.get('instances', []))} tenant(s)")
    users = cfg_for_import.get("users", [])
    print(
        f"🔐 Login: Flask-Login enabled ({len(users)} user(s))"
        if users
        else "⚠️  Login: Disabled (anonymous access)"
    )
    print(f"📊 Dashboard: http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()