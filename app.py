#!/usr/bin/env python3
from mmonit_hub import create_app, load_config, CONFIG_FILE
import sys

# Expose a top-level Flask app for gunicorn (uses default config path)
app = create_app(CONFIG_FILE)

if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else CONFIG_FILE
    cfg = load_config(cfg_path)
    port = int(cfg.get("port", 8080))

    print("M/Monit Hub (Flask) starting…")
    print(f"Config: {cfg_path}")
    print(f"Monitoring {len(cfg.get('instances', []))} tenant(s)")

    users = cfg.get("users", [])
    if users:
        print(f"Login: Flask-Login enabled ({len(users)} user(s))")
    else:
        print("Login: Disabled (anonymous access)")

    print(f"Dashboard: http://localhost:{port}")
    print("Press Ctrl+C to stop\n")

    # Run the dev server; for production use: gunicorn -w 2 -b 0.0.0.0:8082 app:app
    app.run(host="0.0.0.0", port=port)