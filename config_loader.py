import json
import sys
import os
from pathlib import Path

# Default config file locations
LOCAL_CONFIG_FILE = 'mmonit-hub.conf'
USER_CONFIG_FILE = str(Path.home() / '.mmonit-hub.conf')
AUTO_REFRESH_INTERVAL = 30  # Default value

def load_config(config_path=None):
    """Load configuration from JSON file, preferring ~/.mmonit-hub.conf if present."""
    # Determine which config file to use
    if config_path:
        final_path = config_path
    elif os.path.exists(USER_CONFIG_FILE):
        final_path = USER_CONFIG_FILE
    else:
        final_path = LOCAL_CONFIG_FILE

    try:
        with open(final_path, 'r') as f:
            config = json.load(f)

            global AUTO_REFRESH_INTERVAL
            AUTO_REFRESH_INTERVAL = config.get('auto_refresh_seconds', AUTO_REFRESH_INTERVAL)

            # Validate users section
            if 'users' in config and config['users']:
                for user in config['users']:
                    if not all(k in user for k in ['username', 'password', 'tenants']):
                        print("Warning: Invalid user configuration. Each user must have username, password, and tenants.")

            config['_config_source'] = final_path  # record which file was loaded
            print(f"✅ Loaded configuration from: {final_path}")
            return config

    except FileNotFoundError:
        print(f"❌ Error: Config file '{final_path}' not found!")
        print("\nCreate a config file with this format:")
        print(json.dumps({
            "port": 8080,
            "auto_refresh_seconds": 30,
            "users": [
                {
                    "username": "admin",
                    "password": "hashed-password",
                    "tenants": ["*"]
                }
            ],
            "instances": [
                {
                    "name": "tenant1",
                    "url": "https://mmonit1.example.com:8080",
                    "username": "admin",
                    "password": "password1"
                }
            ]
        }, indent=2))
        print("\nNote: Use the --hash-password command to generate password hashes.")
        sys.exit(1)

    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in config file '{final_path}': {e}")
        sys.exit(1)

def get_auto_refresh_interval():
    """Expose the auto-refresh interval from loaded config."""
    return AUTO_REFRESH_INTERVAL