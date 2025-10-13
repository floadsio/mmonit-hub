import json
import sys
from pathlib import Path

# Default config file location
CONFIG_FILE = 'mmonit-hub.conf'
AUTO_REFRESH_INTERVAL = 30 # Default value

def load_config(config_path):
    """Load configuration from JSON file"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            
            # Use globals to modify constants accessible elsewhere (like in mmonit_hub.py)
            global AUTO_REFRESH_INTERVAL
            AUTO_REFRESH_INTERVAL = config.get('auto_refresh_seconds', AUTO_REFRESH_INTERVAL)
            
            # Validate users config
            if 'users' in config and config['users']:
                for user in config['users']:
                    if 'username' not in user or 'password' not in user or 'tenants' not in user:
                        print("Warning: Invalid user configuration. Each user must have username, password, and tenants.")
            
            return config
    except FileNotFoundError:
        print(f"Error: Config file '{config_path}' not found!")
        print(f"\nCreate a config file with this format:")
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
        print("\nNote: Use the --hash-password command to generate password hashes")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}")
        sys.exit(1)

# Function to expose the final interval from config
def get_auto_refresh_interval():
    return AUTO_REFRESH_INTERVAL