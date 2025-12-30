# AGENTS.md - M/Monit Hub Development Guide

This document provides guidance for Claude Code agents working on M/Monit Hub. It covers development workflows, architecture, task decomposition strategies, and code conventions.

## Project Overview

**M/Monit Hub** is a Flask-based monitoring dashboard that aggregates multiple M/Monit instances with optional Healthchecks.io integration. It's a full-stack web application featuring:

- Session-based authentication with PBKDF2 password hashing
- Multi-tenant host aggregation from multiple M/Monit instances
- Healthchecks.io integration for backup/cron monitoring
- Responsive frontend with light/dark theming
- Real-time filtering and auto-refresh capabilities
- Progressive Web App (PWA) support

**Tech Stack:**
- Backend: Flask 3.0+, Flask-Login, Requests
- Frontend: Vanilla JavaScript (no frameworks), HTML5, CSS3
- Server: Gunicorn for production
- Config: JSON-based configuration system

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Browser (PWA)                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ index.html + script.js (739 lines)           │  │
│  │ - Theme management (light/dark)              │  │
│  │ - Filtering (issues, host types)             │  │
│  │ - Auto-refresh polling (/api/data)           │  │
│  │ - Host detail modals                         │  │
│  └──────────────────────────────────────────────┘  │
│                                                      │
│ localStorage: theme prefs, filter state             │
└─────────────────────────────────────────────────────┘
          ↕ HTTP (REST API)
┌─────────────────────────────────────────────────────┐
│            Flask Backend (mmonit_hub/)              │
│  ┌──────────────────────────────────────────────┐  │
│  │ Routes:                                      │  │
│  │ - GET/POST /login (Flask-Login session)     │  │
│  │ - GET /logout                                │  │
│  │ - GET / (dashboard, requires auth)           │  │
│  │ - GET /api/data (JSON API, requires auth)    │  │
│  └──────────────────────────────────────────────┘  │
│                      ↓                              │
│  ┌──────────────────────────────────────────────┐  │
│  │ data_fetcher.py (374 lines)                  │  │
│  │ - query_mmonit_data()                        │  │
│  │ - fetch_healthchecks_for_tenant()            │  │
│  │ - Multi-instance aggregation                 │  │
│  └──────────────────────────────────────────────┘  │
│           ↙                  ↘                      │
│      (API)                (API)                     │
└─────┬──────────────────────────────┬───────────────┘
      ↓                              ↓
┌─────────────────────────┐  ┌──────────────────────┐
│   M/Monit Instances     │  │  Healthchecks.io     │
│ (Multiple, per config)  │  │   (Optional)         │
│ /api/v2/status/*        │  │  /api/v3/checks/     │
└─────────────────────────┘  └──────────────────────┘
```

### Key Design Principles

1. **Configuration-Driven**: All behavior (users, instances, thresholds) is driven by JSON config, not code changes
2. **Multi-Tenant**: Single app instance serves multiple users with different host access levels (isolation via `user.tenants`)
3. **Stateless Backend**: Flask app is horizontally scalable; all state in config + session cookies
4. **Progressive Enhancement**: Frontend works with or without auto-refresh; falls back gracefully
5. **Minimal Dependencies**: Vanilla JS, no frameworks; pure DOM manipulation
6. **Separation of Concerns**: Backend handles auth + aggregation, frontend handles presentation + interaction

## File Structure & Key Files

```
mmonit-hub/
├── app.py                    # CLI entry point + module entry for Gunicorn
├── auth_utils.py (61 lines)  # Password hashing (PBKDF2-HMAC-SHA256)
├── config_loader.py (121 lines) # Config discovery & JSON parsing
├── data_fetcher.py (374 lines)  # M/Monit + Healthchecks.io aggregation
├── mmonit_hub/
│   └── __init__.py (150 lines)  # Flask app factory & routes
├── templates/
│   ├── index.html            # Dashboard UI
│   └── login.html            # Login form
├── static/
│   ├── style.css (348 lines) # Theming with CSS variables
│   ├── script.js (739 lines) # Frontend logic
│   ├── manifest.json         # PWA metadata
│   └── icons/
├── mmonit-hub-example.conf   # Config template (reference)
└── requirements.txt
```

### Critical Files for Understanding Changes

| File | Purpose | When to Modify |
|------|---------|----------------|
| `mmonit_hub/__init__.py` | Flask routes, auth logic | Add API endpoints, change auth flow |
| `data_fetcher.py` | M/Monit + Healthchecks.io aggregation | Add new data sources, fix API issues, add caching |
| `script.js` | Frontend logic, filtering, auto-refresh | Add UI features, change filtering, theming |
| `style.css` | Styling, theming | Adjust colors, layout, responsive design |
| `config_loader.py` | Configuration handling | Change config paths, add new config options |
| `auth_utils.py` | Password verification | Change auth mechanism |

## Development Workflows

### 1. Adding a New Feature

#### Workflow Pattern:
1. **Identify which tier(s) need changes:**
   - Frontend only (script.js, style.css): Filter UI, theme changes, modal interactions
   - Backend only (data_fetcher.py, config): New data source, caching, API integration
   - Full-stack (both tiers): New host view, new aggregation mode

2. **Backend Changes (if needed):**
   - Modify `data_fetcher.py` to fetch/aggregate new data
   - Add config options to `mmonit-hub-example.conf` and `config_loader.py` for feature flags
   - Add new JSON fields to `/api/data` response
   - Consider backward compatibility; old configs should still work

3. **Frontend Changes (if needed):**
   - Update `script.js` to handle new API response fields
   - Add event listeners and filter handlers
   - Update `style.css` for new UI elements
   - Test with localStorage state (theme, filters persist)

4. **Testing:**
   - Use `demo.html` for manual testing without M/Monit backend
   - Test with `--hash-password` to generate test credentials
   - Verify with `make run` and browser devtools

#### Example: Adding a new filter type
```bash
# 1. Update script.js to add filter button and filter logic
# 2. Add filter state to localStorage handler
# 3. Update renderDashboard() to apply new filter
# 4. Add CSS for new filter button (style.css)
# 5. Test with make run
```

### 2. Fixing a Bug

#### Workflow Pattern:
1. **Reproduce**: Use `make run` to test locally, enable browser devtools network tab
2. **Identify scope**:
   - Frontend bug (rendering, interaction): Likely in `script.js` or `style.css`
   - API bug (wrong data, missing fields): Likely in `data_fetcher.py` or `mmonit_hub/__init__.py`
   - Auth bug (login fails, permissions wrong): Check `auth_utils.py` and Flask-Login session
3. **Fix**: Apply minimal change to single file if possible
4. **Verify**: Test with different scenarios (multi-tenant, no Healthchecks, auto-refresh on/off)

### 3. Adding New API Integration (e.g., Prometheus, Zabbix)

#### Workflow Pattern:
1. **Add configuration options:**
   - Update `mmonit-hub-example.conf` with new instance type
   - Modify `config_loader.py` to validate new config fields

2. **Implement data fetcher:**
   - Create new function in `data_fetcher.py` (e.g., `fetch_prometheus_data()`)
   - Follow same return format as `query_mmonit_data()` for consistency
   - Handle API authentication and error cases

3. **Integrate into aggregation:**
   - Modify `/api/data` route in `mmonit_hub/__init__.py` to call new fetcher
   - Merge results into existing host/check data structure

4. **Frontend:** No changes needed if you maintain the same response format

### 4. Deploying Changes

#### Development:
```bash
make venv
make install
make run  # Flask dev server, auto-reloads on changes
```

#### Production (with updated config):
```bash
gunicorn -w 2 -b 0.0.0.0:8082 app:app
```

#### Docker (example):
```dockerfile
FROM python:3.11-slim
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8082", "app:app"]
```

## Code Conventions

### Python

- **Module organization**: Core logic in top-level modules (`auth_utils.py`, `data_fetcher.py`), Flask app in `mmonit_hub/__init__.py`
- **Function naming**: `snake_case` for all functions
- **Class naming**: `PascalCase` for Flask models (e.g., `ConfigUser`)
- **Error handling**: Graceful fallbacks for API failures; log errors but don't crash on missing M/Monit instance
- **Dependencies**: Keep minimal; only use Flask, Flask-Login, Requests, Gunicorn
- **Config-driven behavior**: Never hardcode values that should be configurable (timeouts, thresholds, URLs)

### JavaScript (Vanilla)

- **No external frameworks**: Use pure DOM APIs (querySelector, addEventListener, fetch)
- **Function naming**: `camelCase` for all functions
- **Async pattern**: Use `async/await` with fetch API; wrap in try/catch
- **DOM manipulation**: Use `innerHTML` for safe markup (validated data only), `textContent` for user-facing text
- **State management**: Use `localStorage` for persistent user preferences (theme, filters)
- **Global state**: Keep minimal; use data attributes on DOM elements when possible

### CSS

- **CSS Variables**: Use `--var-name` for colors, spacing, theme-dependent values
- **Selectors**: Class-based selectors preferred over ID-based
- **Theming**: Light/dark themes via `[data-theme="light"]` attribute on root element
- **Responsive**: Mobile-first approach; use media queries for desktop adjustments
- **No frameworks**: Pure CSS3; no Tailwind, Bootstrap, or CSS-in-JS

### Configuration

- **Format**: JSON with nested objects for feature groups
- **Validation**: `config_loader.py` must validate required fields before app starts
- **Defaults**: Reasonable defaults for optional fields (e.g., `auto_refresh_seconds: 30`)
- **Example file**: Keep `mmonit-hub-example.conf` in sync with code changes
- **Secrets**: Users manage secrets via config; never commit real passwords/API keys

## Multi-Tenant Considerations

When adding features, keep these constraints in mind:

1. **User isolation**: A user's `user.tenants` list determines which hosts they can see
   - `["*"]` = access to all tenants
   - `["prod", "staging"]` = only those tenants
   - Frontend should never receive data for unauthorized tenants

2. **API filtering**: `/api/data` endpoint filters results by `current_user.tenants` before returning
   - Always check `current_user.tenants` in backend; never trust frontend
   - Tenant filtering happens in `data_fetcher.py` during aggregation

3. **Config example**:
   ```json
   {
     "users": [
       {"username": "admin", "tenants": ["*"]},
       {"username": "team-a", "tenants": ["prod-a", "staging-a"]}
     ],
     "instances": [
       {"name": "prod-a", ...},
       {"name": "staging-a", ...},
       {"name": "prod-b", ...}
     ]
   }
   ```

## Testing Approach

### Manual Testing
1. **UI Testing**: Use `demo.html` for frontend testing without backend
2. **Integration Testing**: Use `make run` with test config pointing to real M/Monit instance
3. **Multi-user Testing**: Create test config with multiple users, verify isolation
4. **Theme Testing**: Verify light/dark mode CSS variables, localStorage persistence
5. **Mobile Testing**: Browser devtools device emulation for responsive design

### Common Test Scenarios
```bash
# Generate test password hash
python app.py --hash-password

# Run with test config
python app.py --config ./test-config.json

# Test with auto-refresh
# Change auto_refresh_seconds: 5 in config, watch network tab

# Test with no Healthchecks.io
# Set healthchecks.enabled: false in config
```

## Task Decomposition for Parallel Work

### Example: Add New Dashboard Widget

Can be decomposed into:
1. **Backend (Agent 1)**: Add new aggregation logic in `data_fetcher.py`, update `/api/data` response format
2. **Frontend (Agent 2)**: Implement widget rendering in `script.js`, styling in `style.css`
3. **Testing (Agent 1)**: Verify aggregation logic with different M/Monit responses
4. **Testing (Agent 2)**: Verify widget renders correctly with theme changes, responsive layout

**Coordination point**: API response format must be finalized before frontend agent starts

### Example: Add New Configuration Option

Can be decomposed into:
1. **Config parsing**: Update `config_loader.py` to parse new option, update example config
2. **Backend logic**: Use new config option in relevant module (data_fetcher, auth_utils, etc.)
3. **Frontend UI**: If user-visible option, add to settings UI in frontend

**Coordination point**: Config option name and default value must be agreed upfront

## Debugging Tips

### Backend Debugging
- **Check Flask logs**: `make run` shows request/response logs
- **Verify config**: Print loaded config with `python -c "from config_loader import load_config; print(load_config())"`
- **Test API directly**: `curl -H "Authorization: Basic ..." http://localhost:8082/api/data`
- **Check M/Monit auth**: Verify `z_security_check` response in data_fetcher.py

### Frontend Debugging
- **Browser devtools**: Network tab shows `/api/data` responses, Console shows JS errors
- **Theme debugging**: Check `localStorage.getItem('theme')` and `document.documentElement.dataset.theme`
- **Filter debugging**: Check `localStorage.getItem('filterState')` and inspect rendered host cards
- **Auto-refresh**: Check console for fetch errors, network tab for `/api/data` polling

### Common Issues
| Issue | Likely Cause | Debug Step |
|-------|--------------|-----------|
| Login fails | Wrong password hash | Regenerate with `python app.py --hash-password` |
| No hosts shown | User not in tenant | Check config users.tenants vs instances names |
| API returns error | M/Monit unreachable | Verify instance URL, SSL, credentials in config |
| Theme not persisting | localStorage disabled | Check browser settings, devtools Storage tab |
| Auto-refresh not working | JavaScript error | Check browser console for JS errors |

## Performance Considerations

1. **Data fetching**: `/api/data` aggregates all M/Monit instances serially; consider caching/parallel requests for large deployments
2. **Frontend rendering**: `renderDashboard()` re-renders all host cards; for 1000+ hosts, optimize with virtual scrolling
3. **Memory**: Healthchecks data cached in memory; stale cache pruned based on `check_cache_age_threshold`
4. **Network**: Auto-refresh polling every N seconds; keep `auto_refresh_seconds` reasonable (≥30s for production)

## Common Patterns & Anti-Patterns

### ✅ Good Patterns

```python
# Config-driven behavior
if config.get('healthchecks', {}).get('enabled'):
    # Fetch and merge healthchecks data

# Graceful error handling
try:
    response = requests.get(url, timeout=5)
except requests.RequestException:
    # Log and continue, don't crash
    results['errors'].append(f"Failed to fetch {url}")
```

```javascript
// Async/await for API calls
async function fetchData() {
    try {
        const response = await fetch('/api/data');
        const data = await response.json();
        renderDashboard(data);
    } catch (error) {
        console.error('Failed to fetch data:', error);
        // Show error to user, retry later
    }
}

// Use data attributes instead of global state
element.dataset.tenantId = tenant.id;
element.addEventListener('click', (e) => {
    const tenantId = e.target.dataset.tenantId;
});
```

### ❌ Anti-Patterns (Avoid)

```python
# Hardcoded values in code (should be config)
DISK_WARNING_PCT = 80  # NO - put in config

# Trusting frontend data for security decisions
if request.args.get('tenants'):  # NO - use session, never trust frontend
```

```javascript
// Global variables for state (use localStorage or data attributes)
let filterState = {}; // NO - use localStorage or DOM state

// innerHTML with unsanitized user input
element.innerHTML = userInput; // NO - only safe for validated data

// Polling with fixed timeout (should be configurable)
setInterval(fetchData, 5000); // NO - use config or dynamic timing
```

## Security Considerations

1. **Password hashing**: Always use PBKDF2 via `auth_utils.hash_password()`, never store plaintext
2. **Session security**: Flask-Login handles session cookies; ensure `secret_key` is strong and unique per deployment
3. **HTTPS**: In production, always use HTTPS (enforce in reverse proxy/load balancer)
4. **API auth**: Never expose API keys in frontend; keep M/Monit/Healthchecks credentials in backend config
5. **CORS**: Frontend should only call same-origin `/api/data` endpoint
6. **Input validation**: Validate user input at system boundaries (login form, API params)

## Platform-Specific Deployment

M/Monit Hub supports multiple Unix-like platforms with platform-specific deployment scripts:

### Linux (systemd)

- **Service file**: `deployment/mmonit-hub.service`
- **Installer**: `deployment/install-service.sh`
- **Installation**: `sudo deployment/install-service.sh syseng /home/syseng/mmonit-hub`
- **Commands**: `sudo systemctl {start|stop|restart|status} mmonit-hub`
- **Logs**: `sudo journalctl -u mmonit-hub -f`
- **Security**: Service uses `ProtectSystem=strict` with read-only code directory

### OpenBSD (rc.d)

- **Service file**: `deployment/mmonit-hub.rc`
- **Installer**: `deployment/install-rc.sh`
- **Installation**: `doas deployment/install-rc.sh syseng /home/syseng/mmonit-hub`
- **Commands**: `doas rcctl {start|stop|restart|check} mmonit_hub` (note underscore, not hyphen)
- **Logs**: `tail -f /home/syseng/mmonit-hub/logs/error.log`
- **Privilege**: Uses `doas` instead of `sudo` (OpenBSD convention)
- **Note**: rc.d service names use underscores (mmonit_hub, not mmonit-hub)

### Platform Detection in Makefile

The `make update-restart` target automatically detects the platform:

```bash
if systemctl is-active mmonit-hub 2>/dev/null
  → Uses: sudo systemctl restart mmonit-hub      (Linux)
elif rcctl check mmonit_hub 2>/dev/null
  → Uses: doas rcctl restart mmonit_hub          (OpenBSD)
else
  → Manual restart required (other systems)
```

### Manual Deployment (All Platforms)

If you don't want to install a service manager script:

```bash
# Development mode (foreground)
make run

# Production mode with gunicorn (manual management)
make gunicorn

# In tmux/screen for background execution
tmux new-session -d -s mmonit-hub 'cd /home/syseng/mmonit-hub && make gunicorn'
```

### Key Differences by Platform

| Aspect | Linux | OpenBSD | macOS |
|--------|-------|---------|-------|
| Init system | systemd | rc.d | launchd |
| Service installer | install-service.sh | install-rc.sh | Manual |
| Privilege escalation | sudo | doas | sudo |
| Service name | mmonit-hub | mmonit_hub | N/A |
| Config location | ~/.config/mmonit-hub/ | ~/.config/mmonit-hub/ | ~/Library/Preferences/ |

### Shell Compatibility

- **update.sh**: Uses bash (install with `pkg_add bash` on OpenBSD if needed)
- **rc.d script**: Uses ksh (standard on OpenBSD)
- **install-*.sh**: Uses POSIX sh (portable across systems)

### OpenBSD-Specific Considerations

1. **doas configuration** (optional, for passwordless service restart):
   ```
   # /etc/doas.conf
   permit nopass keepenv syseng as root cmd rcctl args restart mmonit_hub
   ```

2. **Service persistence across reboots**:
   ```bash
   doas rcctl enable mmonit_hub
   ```

3. **Gunicorn daemon mode**: Uses `/var/run/mmonit-hub.pid` for process tracking
4. **Logs**: Check both error and access logs in `$INSTALL_DIR/logs/`

## Future Roadmap Guidance

When adding future features, consider:
- **More integrations**: Follow the `data_fetcher.py` pattern for new sources
- **Caching layer**: Redis for distributed deployments
- **Alerting**: Webhook support for critical issues
- **Advanced filtering**: Save filter presets, advanced query syntax
- **Mobile app**: Repurpose frontend as PWA or native app

---

**Last Updated**: 2025-12-30
**Version**: 1.0
