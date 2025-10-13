# M/Monit Hub (Flask Edition)

A lightweight, multi-tenant monitoring dashboard that aggregates multiple [M/Monit](https://mmonit.com/) instances into a single unified interface — now built with **Flask** for improved modularity, extensibility, and authentication.

---

## 🚀 What’s New (Flask release)

- Rebuilt using **Flask** with cleaner structure (`app.py`, `mmonit_hub/` package)
- **Session-based login** instead of HTTP Basic Auth
- Easier deployment via **Gunicorn** or `flask run`
- Simplified setup using a **Makefile** (`make venv`, `make run`, `make clean`)
- Improved UI: clearer alerts, disk usage warnings, and color consistency
- Added **browser icon (favicon)** and `manifest.json` for PWA support
- Extended host detail view with full service list and disk usage alerts
- ⚡ Auto-refresh updates without page reload

---

## 🎯 Live Demo

**[View Live Demo →](https://floadsio.github.io/mmonit-hub/demo.html)**

Try the interactive demo with fake data to see how M/Monit Hub works.

### Dark Theme
![M/Monit Hub - Dark Theme](screenshot-dark.jpg)

### Light Theme
![M/Monit Hub - Light Theme](screenshot-light.jpg)

---

## Features

- **Session Authentication** – Secure web login with password hashing (no Basic Auth)
- **User Isolation** – Configure which **tenants** each dashboard user can access
- **Multi-Tenant Support** – Aggregate multiple M/Monit instances in one UI
- ⏱️ **Auto Refresh** – Live updates every N seconds (configurable)
- **Disk Alerts** – Warnings for high disk usage (default 80% warn / 90% error)
- ⚠️ **Visual Alerts** – Red/Yellow status cards for quick problem detection
- **Detailed Host View** – Click any host to see full service list and filesystem info
- **Light/Dark Themes** – Automatic or manual theme switching
- **Responsive Layout** – Works on desktop, tablet, and mobile
- **PWA-ready** – Includes favicon and manifest for browser/app integration

---

## 🧩 Project Structure

```
mmonit-hub/
├── app.py                      # Flask app entrypoint
├── auth_utils.py               # User login/session management
├── config_loader.py            # Config file loader and validator
├── data_fetcher.py             # Fetches and aggregates M/Monit API data
├── frontend_html.py            # (legacy helper; kept for reference)
├── mmonit_hub/                 # Flask package (namespace)
│   └── __init__.py
├── static/                     # CSS, JS, icons, manifest
│   ├── style.css
│   ├── script.js
│   ├── manifest.json
│   └── icons/
│       ├── favicon.ico
│       └── favicon-512.png
├── templates/                  # Flask Jinja2 templates
│   ├── index.html
│   └── login.html
├── Makefile
├── mmonit-hub-example.conf     # Example config file (do not commit real conf)
├── requirements.txt
├── LICENSE
└── README.md
```

---

## ⚙️ Requirements

- Python 3.8+
- One or more [M/Monit](https://mmonit.com/) instances with HTTP API enabled
- Recommended: `gunicorn` for production

---

## 🧰 Installation & Setup

### 1️⃣ Clone the repository

```bash
git clone https://github.com/floadsio/mmonit-hub.git
cd mmonit-hub
```

### 2️⃣ Create a virtual environment

```bash
make venv
```

### 3️⃣ Activate and install dependencies

```bash
source .venv/bin/activate
make install
```

### 4️⃣ Copy and edit configuration

```bash
cp mmonit-hub-example.conf mmonit-hub.conf
```

Edit `mmonit-hub.conf` to define your dashboard users and M/Monit instances.

**Example:**

```json
{
  "port": 8082,
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
      "name": "Production EU",
      "url": "https://mmonit.example.com:8080",
      "username": "admin",
      "password": "secret",
      "verify_ssl": false
    }
  ]
}
```

### 5️⃣ Generate password hashes

```bash
python3 app.py --hash-password
```

Paste the generated hash into your config file.

### 6️⃣ Run the app

Development mode:

```bash
make run
```

Production mode:

```bash
gunicorn -w 2 -b 0.0.0.0:8082 app:app
```

---

## 🧹 Makefile Commands

| Command | Description |
|----------|-------------|
| `make venv` | Create Python virtual environment |
| `make install` | Install dependencies inside `.venv` |
| `make run` | Run Flask app (`flask run`) |
| `make gunicorn` | Run with Gunicorn (production-ready) |
| `make clean` | Remove `.venv`, cache, and temp files |
| `make reset` | Clean + recreate venv and reinstall |

---

## 🔍 Dashboard Overview

- **Tenants**: Each represents one M/Monit instance
- **Host cards**: Hostname, CPU, memory, and disk usage
- **Color codes**:
  - 🟢 **OK** – all services running
  - 🟡 **Warning** – partial issues or high disk usage
  - 🔴 **Error** – service down or unreachable
- **Host modal**: Full detail view with services, disks, and a link to M/Monit

---

## ⚙️ Configuration Notes

- `auto_refresh_seconds`: How often data refreshes automatically (0 = disable)
- Disk usage alert thresholds default to 80% (warning) and 90% (error)
- `verify_ssl` can be disabled for self-signed M/Monit certs

---

## 🔒 Security Best Practices

- Use HTTPS for all M/Monit URLs
- Store `mmonit-hub.conf` outside public directories
- Don’t commit real configs to Git (use `mmonit-hub-example.conf`)
- If exposing publicly, run behind a reverse proxy with TLS and rate-limiting

---

## 🧠 Troubleshooting

**No hosts appear**
- Check API credentials and tenant names

**401 Unauthorized**
- Verify login and hashed password in the config

**SSL errors**
- Set `"verify_ssl": false` or use valid CA-signed certs

**Port already in use**
- Change `port` in config or free it (`lsof -i :8082`)

**Disk usage not visible**
- Ensure M/Monit reports filesystem stats for hosts

---

## 🧩 Development

To reset everything and start fresh:

```bash
make clean
make venv
make install
make run
```

---

## 📜 License

MIT License – see `LICENSE`.

---

## 🏗️ Credits

Created by [floads.io](https://floads.io)  
Built for monitoring multiple [M/Monit](https://mmonit.com/) instances.

---

## 🧩 Support

- Issues: [GitHub Issues](https://github.com/floadsio/mmonit-hub/issues)
- Documentation: [M/Monit API Docs](https://mmonit.com/documentation/http-api/)

---

> **Note:** This is an independent tool and is not affiliated with or endorsed by Tildeslash Ltd or M/Monit.
