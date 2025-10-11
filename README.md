# MMonit Hub

A lightweight, multi-tenant monitoring dashboard that aggregates multiple M/Monit instances into a single unified interface.

## 🎯 Live Demo

**[View Live Demo →](https://floadsio.github.io/mmonit-hub/demo.html)**

Try the interactive demo with fake data to see how MMonit Hub works.

### Dark Theme
![MMonit Hub - Dark Theme](screenshot-dark.jpg)

### Light Theme
![MMonit Hub - Light Theme](screenshot-light.jpg)

-----

## Features

  - 🔒 **Secure Access** - Uses **HTTP Basic Authentication** with hashed passwords for dashboard access.
  - 🧑‍💻 **User Isolation** - Configure which **tenants** each dashboard user can see.
  - 🔄 **Multi-Tenant Support** - Monitor multiple M/Monit instances from one dashboard.
  - ⏱️ **Update Visibility** - Displays **last fetch time** and **auto-refresh interval**.
  - 🎨 **Dark/Light Theme** - Automatic system theme detection with manual override.
  - 📊 **Real-Time Monitoring** - Auto-refresh with configurable intervals.
  - 🔍 **Smart Sorting** - Sort by issues, name, host count, CPU, or memory usage.
  - 💾 **Disk Space Monitoring** - View filesystem usage across all hosts.
  - ⚠️ **Issue Highlighting** - Instantly see which services have problems.
  - 📱 **Responsive Design** - Works on desktop, tablet, and mobile.
  - 🖱️ **Interactive** - Click hosts for detailed information, click tenants to open M/Monit.

-----

## Screenshots

### Dashboard Overview

Shows all tenants and hosts at a glance with status indicators.

### Host Details

Click any host to see detailed information including CPU, memory, disk space, and service issues.

### Theme Support

Supports both dark and light themes with automatic detection.

-----

## Requirements

  - Python 3.6+
  - M/Monit instance(s) with API access

-----

## Installation

1.  Clone the repository:

<!-- end list -->

```bash
git clone https://github.com/floadsio/mmonit-hub.git
cd mmonit-hub
```

2.  Install dependencies:

<!-- end list -->

```bash
pip3 install -r requirements.txt
```

3.  Create your configuration file:

<!-- end list -->

```bash
cp mmonit-hub.conf.example mmonit-hub.conf
```

4.  **Generate a password hash** for your dashboard users:

<!-- end list -->

```bash
python3 mmonit-hub.py --hash-password
```

*(You will be prompted to enter and confirm a password. The output hash is what you place in your config file.)*

5.  Edit `mmonit-hub.conf` with your M/Monit instances and dashboard users:

<!-- end list -->

```json
{
  "port": 8082,
  "auto_refresh_seconds": 30,
  "users": [
    {
      "username": "admin",
      "password": "hashed-password-from-step-4",
      "tenants": ["*"] 
    },
    {
      "username": "viewer",
      "password": "another-hashed-password",
      "tenants": ["Production US-East", "Production EU"]
    }
  ],
  "instances": [
    {
      "name": "Production US-East",
      "url": "https://mmonit-us.example.com:8080",
      "username": "mmonit-user",
      "password": "mmonit-password",
      "verify_ssl": false,
      "api_version": "2"
    }
  ]
}
```

-----

## Configuration

### Configuration Options

  - **port**: Port for the web dashboard (default: 8080)
  - **auto\_refresh\_seconds**: Auto-refresh interval in seconds (0 to disable, default: 30)
  - **users**: Array of dashboard users for Basic Authentication.
  - **instances**: Array of M/Monit instances to monitor.

### User Configuration (for Dashboard Access)

  - **username**: The username for the dashboard's Basic Auth.
  - **password**: **The PBKDF2 hashed password** generated using `--hash-password`.
  - **tenants**: A list of `instance.name` strings this user can view. Use `["*"]` to allow viewing all defined instances.

### Instance Configuration (for M/Monit API Access)

  - **name**: Display name for the tenant (must match name used in the `users.tenants` list).
  - **url**: M/Monit URL (including protocol and port).
  - **username**: M/Monit username (used for API login).
  - **password**: M/Monit password (used for API login).
  - **verify\_ssl**: Enable/disable SSL certificate verification (default: false).
  - **api\_version**: M/Monit API version (default: "2").

-----

## Usage

Start the dashboard:

```bash
python3 mmonit-hub.py
```

Then open your browser to:

```
http://localhost:8082
```

*(You will be immediately prompted for a username and password defined in your `users` block.)*

-----

## Features in Detail

### Dashboard View

  - **Status Cards**: Quick overview of **total tenants, hosts, services**, and issues.
  - **Last Updated**: Shows the time of the last successful data fetch from all instances.
  - **Tenant Cards**: Shows all hosts grouped by M/Monit instance.
  - **Color Coding**:
      - 🟢 Green: All services running
      - 🟡 Yellow: Warning state
      - 🔴 Red: Service errors or connection issues
  - **Host Cards**: Display hostname, status, CPU, memory, and max disk usage.
  - **Issue Preview**: Shows problematic services directly on host cards.

### Host Details Modal

Click any host to see:

  - Full status information
  - **Detailed CPU and memory usage**
  - **All filesystem/disk capacity and usage**
  - **Detailed service issues** with status messages
  - Events count and heartbeat status
  - Direct link to view host in M/Monit

### Sorting Options

  - **Issues First**: Prioritize hosts with problems (default)
  - **Name**: Alphabetical by tenant name
  - **Host Count**: Tenants with most hosts first
  - **CPU Usage**: Highest average CPU usage first
  - **Memory Usage**: Highest average memory usage first

### Theme Management

  - Automatically detects system dark/light mode preference
  - Manual toggle available (persists in browser)
  - Smooth transitions between themes

-----

## API Compatibility

MMonit Hub uses the M/Monit HTTP API. It's been tested with:

  - M/Monit API v2 (recommended)
  - M/Monit API v1 (legacy)

See the [M/Monit HTTP-API documentation](https://mmonit.com/documentation/http-api/) for details.

-----

## Security Considerations

  - **Dashboard Authentication**: HTTP Basic Auth uses hashed passwords for the dashboard, which is more secure than storing plain text.
  - **Credentials**: Store your `mmonit-hub.conf` securely.
  - **Network**: Consider running behind a reverse proxy with authentication.
  - **SSL**: Enable `verify_ssl: true` in production environments with valid certificates.
  - **Firewall**: Restrict access to the dashboard port.

-----

## Troubleshooting

### Connection Refused

  - Verify Python is installed: `python3 --version`
  - Check if port is already in use: `lsof -i :8082` (or your configured port)
  - Try a different port in the config file

### HTTP 401 Unauthorized (Dashboard)

  - Check the **username** and **password** entered in the browser prompt against the `users` block in `mmonit-hub.conf`.
  - Ensure the password hash is correctly generated using `--hash-password`.

### HTTP 404 Errors

  - Verify your M/Monit URL is correct.
  - Check that the API version matches your M/Monit installation.
  - Ensure credentials in the `instances` block are correct.

### SSL Certificate Errors

  - Set `verify_ssl: false` for self-signed certificates.
  - Or add your CA certificate to your system's trust store.

### No Hosts Showing

  - Check M/Monit has hosts registered.
  - Verify API credentials (`instances` block) have proper permissions on the M/Monit side.
  - Check if the dashboard user is restricted by the `tenants` list in the `users` block.

### Slow Performance

  - Reduce `auto_refresh_seconds` or set to 0.
  - Check network latency to M/Monit instances.

-----

## Contributing

Contributions are welcome\! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details

## Credits

Created by [floads.io](https://floads.io)

Built for monitoring multiple [M/Monit](https://mmonit.com/) instances.

## Support

  - Issues: [GitHub Issues](https://github.com/floadsio/mmonit-hub/issues)
  - Documentation: [M/Monit API Docs](https://mmonit.com/documentation/http-api/)

-----

**Note**: This is an unofficial tool and is not affiliated with or endorsed by Tildeslash Ltd or M/Monit.