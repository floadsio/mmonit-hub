# MMonit Hub

A lightweight, multi-tenant monitoring dashboard that aggregates multiple M/Monit instances into a single unified interface.

## 🎯 Live Demo

**[View Live Demo →](https://floadsio.github.io/mmonit-hub/demo.html)**

Try the interactive demo with fake data to see how MMonit Hub works.

### Dark Theme
![MMonit Hub - Dark Theme](screenshot-dark.jpg)

### Light Theme
![MMonit Hub - Light Theme](screenshot-light.jpg)

## Features

- 🔄 **Multi-Tenant Support** - Monitor multiple M/Monit instances from one dashboard
- 🎨 **Dark/Light Theme** - Automatic system theme detection with manual override
- 📊 **Real-Time Monitoring** - Auto-refresh with configurable intervals
- 🔍 **Smart Sorting** - Sort by issues, name, host count, CPU, or memory usage
- 💾 **Disk Space Monitoring** - View filesystem usage across all hosts
- ⚠️ **Issue Highlighting** - Instantly see which services have problems
- 📱 **Responsive Design** - Works on desktop, tablet, and mobile
- 🖱️ **Interactive** - Click hosts for detailed information, click tenants to open M/Monit
- 🎯 **Zero Dependencies** - Just Python and a browser

## Screenshots

### Dashboard Overview
Shows all tenants and hosts at a glance with status indicators.

### Host Details
Click any host to see detailed information including CPU, memory, disk space, and service issues.

### Theme Support
Supports both dark and light themes with automatic detection.

## Requirements

- Python 3.6+
- M/Monit instance(s) with API access

## Installation

1. Clone the repository:
```bash
git clone https://github.com/floadsio/mmonit-hub.git
cd mmonit-hub
```

2. Install dependencies:
```bash
pip3 install -r requirements.txt
```

3. Create your configuration file:
```bash
cp mmonit-hub.conf.example mmonit-hub.conf
```

4. Edit `mmonit-hub.conf` with your M/Monit instances:
```json
{
  "port": 8080,
  "auto_refresh_seconds": 30,
  "instances": [
    {
      "name": "Production",
      "url": "https://mmonit.example.com:443",
      "username": "admin",
      "password": "your-password",
      "verify_ssl": false,
      "api_version": "2"
    }
  ]
}
```

## Configuration

### Configuration Options

- **port**: Port for the web dashboard (default: 8080)
- **auto_refresh_seconds**: Auto-refresh interval in seconds (0 to disable, default: 30)
- **instances**: Array of M/Monit instances to monitor

### Instance Configuration

- **name**: Display name for the tenant
- **url**: M/Monit URL (including protocol and port)
- **username**: M/Monit username
- **password**: M/Monit password
- **verify_ssl**: Enable/disable SSL certificate verification (default: false)
- **api_version**: M/Monit API version (default: "2")

## Usage

Start the dashboard:
```bash
python3 mmonit-hub.py
```

Or with a custom config file:
```bash
python3 mmonit-hub.py /path/to/config.conf
```

Then open your browser to:
```
http://localhost:8080
```

## Features in Detail

### Dashboard View
- **Status Cards**: Quick overview of total tenants, hosts, and issues
- **Tenant Cards**: Shows all hosts grouped by M/Monit instance
- **Color Coding**: 
  - 🟢 Green: All services running
  - 🟡 Yellow: Warning state
  - 🔴 Red: Service errors or connection issues
- **Host Cards**: Display hostname, status, CPU, memory, and disk usage
- **Issue Preview**: Shows problematic services directly on host cards

### Host Details Modal
Click any host to see:
- Full status information
- CPU and memory usage
- All filesystem/disk information
- Detailed service issues with status messages
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

## Development

The project structure:
```
mmonit-hub/
├── mmonit-hub.py           # Main application
├── mmonit-hub.conf         # Configuration file
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

### Adding Features

The application is built with:
- **Backend**: Python 3 with `requests` library
- **Frontend**: Vanilla JavaScript (no frameworks)
- **Styling**: Pure CSS with CSS variables for theming

## API Compatibility

MMonit Hub uses the M/Monit HTTP API. It's been tested with:
- M/Monit API v2 (recommended)
- M/Monit API v1 (legacy)

See the [M/Monit HTTP-API documentation](https://mmonit.com/documentation/http-api/) for details.

## Security Considerations

- **Credentials**: Store your `mmonit-hub.conf` securely
- **Network**: Consider running behind a reverse proxy with authentication
- **SSL**: Enable `verify_ssl: true` in production environments with valid certificates
- **Firewall**: Restrict access to the dashboard port

## Troubleshooting

### Connection Refused
- Verify Python is installed: `python3 --version`
- Check if port is already in use: `lsof -i :8080`
- Try a different port in the config file

### HTTP 404 Errors
- Verify your M/Monit URL is correct
- Check that the API version matches your M/Monit installation
- Ensure credentials are correct

### SSL Certificate Errors
- Set `verify_ssl: false` for self-signed certificates
- Or add your CA certificate to your system's trust store

### No Hosts Showing
- Check M/Monit has hosts registered
- Verify API credentials have proper permissions
- Check browser console for errors

### Slow Performance
- Reduce `auto_refresh_seconds` or set to 0
- Consider monitoring fewer hosts per instance
- Check network latency to M/Monit instances

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details

## Credits

Created by [floads.io](https://floads.io)

Built for monitoring multiple [M/Monit](https://mmonit.com/) instances.

## Support

- Issues: [GitHub Issues](https://github.com/floadsio/mmonit-hub/issues)
- Documentation: [M/Monit API Docs](https://mmonit.com/documentation/http-api/)

---

**Note**: This is an unofficial tool and is not affiliated with or endorsed by Tildeslash Ltd or M/Monit.