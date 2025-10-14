# config_loader.py
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

# Defaults
DEFAULT_BASENAME = "mmonit-hub.conf"
AUTO_REFRESH_INTERVAL = 30  # default, can be overridden by config

# Search order:
# 1) explicit CLI arg
# 2) env var MMONIT_HUB_CONFIG
# 3) CWD: ./mmonit-hub.conf
# 4) $HOME/.mmonit-hub.conf
# 5) $HOME/.config/mmonit-hub/mmonit-hub.conf
CANDIDATES_REL = [
    Path(DEFAULT_BASENAME),
]
CANDIDATES_HOME = [
    Path.home() / ".mmonit-hub.conf",
    Path.home() / ".config" / "mmonit-hub" / DEFAULT_BASENAME,
]


def _first_existing(paths: list[Path]) -> Optional[Path]:
    for p in paths:
        if p.is_file():
            return p
    return None


def resolve_config_path(cli_path: Optional[str] = None) -> Tuple[Path, str]:
    """
    Decide which config path to use and return (path, source_label)
    """
    # 1) CLI arg
    if cli_path:
        p = Path(cli_path).expanduser().resolve()
        return p, "cli"

    # 2) env var
    env = os.getenv("MMONIT_HUB_CONFIG")
    if env:
        p = Path(env).expanduser().resolve()
        return p, "env"

    # 3) cwd
    cwd_hit = _first_existing([Path.cwd() / c for c in CANDIDATES_REL])
    if cwd_hit:
        return cwd_hit.resolve(), "cwd"

    # 4/5) home candidates
    home_hit = _first_existing(CANDIDATES_HOME)
    if home_hit:
        return home_hit.resolve(), "home"

    # default to ./mmonit-hub.conf even if missing (load_config will error nicely)
    return (Path.cwd() / DEFAULT_BASENAME).resolve(), "default"


def load_config(cli_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration JSON and set globals. Adds '_config_source' to the dict.
    """
    global AUTO_REFRESH_INTERVAL

    path, source = resolve_config_path(cli_path)
    try:
        with open(path, "r") as f:
            cfg = json.load(f)

        # record where we loaded from
        cfg["_config_path"] = str(path)
        cfg["_config_source"] = source

        # adopt auto refresh
        AUTO_REFRESH_INTERVAL = cfg.get("auto_refresh_seconds", AUTO_REFRESH_INTERVAL)

        # sanity check users
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
                    "api_version": "2",
                }
            ],
        }
        print(f"Error: Config file '{path}' not found!\n")
        print("Create a config file with this format:")
        print(json.dumps(example, indent=2))
        print("\nNote: Use --hash-password to generate password hashes")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}")
        sys.exit(1)


def get_auto_refresh_interval() -> int:
    return AUTO_REFRESH_INTERVAL