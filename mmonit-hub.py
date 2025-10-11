#!/usr/bin/env python3
"""
MMonit Hub - Multi-tenant monitoring dashboard (with Basic Auth, Mobile Responsiveness, and Live Filter)
"""

import json
import requests
import sys
import os
import secrets
import hashlib
import hmac
import base64
import re 
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from pathlib import Path
from http import HTTPStatus
import socket
from datetime import datetime, timezone
from collections import Counter 

# Default config file location
CONFIG_FILE = 'mmonit-hub.conf'

# Auto-refresh interval in seconds (0 = disabled)
AUTO_REFRESH_INTERVAL = 30

LAST_FETCH_TIME = None 

# --- AUTH UTILITY FUNCTIONS ---

def hash_password(password, salt=None):
    """Hash password with salt using PBKDF2"""
    if salt is None:
        salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}${pwd_hash.hex()}"

def verify_password(password, password_hash):
    """Verify password against hash"""
    try:
        salt, hash_value = password_hash.split('$')
        return hmac.compare_digest(hash_password(password, salt), password_hash)
    except:
        return False

# --- CONFIG LOADING ---

def load_config(config_path):
    """Load configuration from JSON file"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            # Set auto_refresh from config or use default
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

# --- QUERY DATA ---

def query_mmonit_data(instances, allowed_tenants=None):
    """Aggregate data from all MMonit instances"""
    result = []
    
    for instance in instances:
        name = instance['name']
        
        # Filter by allowed tenants (handles ["*"] for all access)
        if allowed_tenants and "*" not in allowed_tenants and name not in allowed_tenants:
            continue
            
        url = instance['url']
        username = instance['username']
        password = instance['password']
        verify_ssl = instance.get('verify_ssl', False)
        
        try:
            # Create a session to maintain cookies
            session = requests.Session()
            
            # Step 1: Get the session cookie
            session.get(f"{url}/index.csp", timeout=10, verify=verify_ssl)
            
            # Step 2: Login with credentials and disable CSRF for API access
            login_response = session.post(
                f"{url}/z_security_check",
                data={
                    'z_username': username,
                    'z_password': password,
                    'z_csrf_protection': 'off'
                },
                timeout=10,
                verify=verify_ssl
            )
            
            if login_response.status_code != 200:
                result.append({
                    'tenant': name,
                    'url': url,
                    'error': f'Login failed: HTTP {login_response.status_code}',
                    'hosts': [],
                })
                continue
            
            # Step 3: Query the API endpoint with pagination
            api_version = instance.get('api_version', '2')
            response = session.get(
                f"{url}/api/{api_version}/status/hosts/list",
                params={'results': 1000},  # Request up to 1000 hosts
                timeout=10,
                verify=verify_ssl
            )
            
            if response.status_code == 200:
                data = response.json()
                hosts = data.get('records', [])
                
                # Step 4: Fetch detailed info for each host to get disk space, services, OS
                for host in hosts:
                    try:
                        detail_response = session.get(
                            f"{url}/api/{api_version}/status/hosts/get",
                            params={'id': host['id']},
                            timeout=10,
                            verify=verify_ssl
                        )
                        if detail_response.status_code == 200:
                            detail_data = detail_response.json()
                            
                            # --- OS EXTRACTION ---
                            host_records = detail_data.get('records', {}).get('host', {})
                            platform = host_records.get('platform', {})
                            
                            # OS Info
                            host['os_name'] = platform.get('name', 'OS N/A')
                            host['os_release'] = platform.get('release', '') # e.g., '14.3-RELEASE-p3' or '12.0.12'
                            
                            # Uptime is intentionally REMOVED
                            # --- END OS EXTRACTION ---

                            # Extract filesystem info and issues from services
                            filesystems = []
                            issues = []
                            services = host_records.get('services', [])
                            
                            host['service_count'] = len(services) 
                            
                            for service in services:
                                # Track services with issues
                                if service.get('led') in [0, 1]:  # red (0) or yellow (1)
                                    issues.append({
                                        'name': service.get('name', 'Unknown'),
                                        'type': service.get('type', 'Unknown'),
                                        'status': service.get('status', 'Unknown'),
                                        'led': service.get('led')
                                    })
                                
                                if service.get('type') == 'Filesystem':
                                    stats = service.get('statistics', [])
                                    fs_info = {
                                        'name': service.get('name', 'Unknown'),
                                        'usage_percent': None,
                                        'usage_mb': None,
                                        'total_mb': None
                                    }
                                    for stat in stats:
                                        if stat.get('type') == 18:  # space usage percent
                                            fs_info['usage_percent'] = stat.get('value')
                                        elif stat.get('type') == 19:  # space usage megabyte
                                            fs_info['usage_mb'] = stat.get('value')
                                        elif stat.get('type') == 20:  # space total
                                            fs_info['total_mb'] = stat.get('value')
                                    if fs_info['usage_percent'] is not None:
                                        filesystems.append(fs_info)
                            host['filesystems'] = filesystems
                            host['issues'] = issues
                        else:
                            host['filesystems'] = []
                            host['issues'] = []
                            host['service_count'] = 0
                            host['os_name'] = 'OS N/A'
                            host['os_release'] = ''
                    except Exception as e:
                        host['filesystems'] = []
                        host['issues'] = []
                        host['service_count'] = 0
                        host['os_name'] = 'OS N/A'
                        host['os_release'] = ''

                
                # Convert to our format with hosts array
                result.append({
                    'tenant': name,
                    'url': url,
                    'hosts': hosts,
                })
            else:
                result.append({
                    'tenant': name,
                    'url': url,
                    'error': f'API error: HTTP {response.status_code}',
                    'hosts': [],
                })
                
        except requests.exceptions.Timeout:
            result.append({
                'tenant': name,
                'url': url,
                'error': 'Connection timeout',
                'hosts': [],
            })
        except requests.exceptions.ConnectionError:
            result.append({
                'tenant': name,
                'url': url,
                'error': 'Connection failed',
                'hosts': [],
            })
        except Exception as e:
            result.append({
                'tenant': name,
                'url': url,
                'error': str(e),
                'hosts': [],
            })
    
    return result

# --- HTML CONTENT ---

HTML_CONTENT = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>MMonit Hub</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --bg-tertiary: #0f172a;
            --text-primary: #e2e8f0;
            --text-secondary: #94a3b8;
            --border-color: #334155;
            --border-subtle: #64748b;
        }
        
        [data-theme="light"] {
            --bg-primary: #f8fafc;
            --bg-secondary: #ffffff;
            --bg-tertiary: #f1f5f9;
            --text-primary: #0f172a;
            --text-secondary: #64748b;
            --border-color: #e2e8f0;
            --border-subtle: #cbd5e1;
        }
        
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            padding: 20px;
            transition: background-color 0.3s, color 0.3s;
        }
        .header {
            background: var(--bg-secondary);
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #3b82f6;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap; 
        }
        .header-content {
            margin-right: 20px;
        }
        .header-content h1 { font-size: 24px; margin-bottom: 8px; }
        .subtitle { color: var(--text-secondary); font-size: 14px; }
        
        .controls {
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap; 
        }
        
        .user-info { 
            font-size: 14px;
            color: #3b82f6;
            padding: 8px 12px;
            border-radius: 4px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            white-space: nowrap;
        }

        /* --- Unified Logout Button Style (matches theme toggle & dropdown) --- */
        .logout-btn {
            padding: 8px 12px;
            border-radius: 4px;
            border: 1px solid var(--border-color);
            background: var(--bg-tertiary);
            color: var(--text-primary);
            cursor: pointer;
            font-size: 14px;
            text-decoration: none;
            display: inline-block;
            transition: background 0.2s, color 0.2s;
        }

        .logout-btn:hover {
            background: var(--border-color);
            color: var(--text-primary);
        }

        .sort-dropdown {
            padding: 8px 12px;
            border-radius: 4px;
            border: 1px solid var(--border-color);
            background: var(--bg-tertiary);
            color: var(--text-primary);
            font-size: 14px;
            cursor: pointer;
        }
        
        .theme-toggle {
            padding: 8px 12px;
            border-radius: 4px;
            border: 1px solid var(--border-color);
            background: var(--bg-tertiary);
            color: var(--text-primary);
            cursor: pointer;
            font-size: 14px;
        }
        
        .theme-toggle:hover {
            background: var(--border-color);
        }
        
        .tenant {
            background: var(--bg-secondary);
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            border-left: 4px solid var(--border-subtle);
        }
        .tenant.error { border-left-color: #ef4444; }
        .tenant.issues { border-left-color: #f59e0b; }
        .tenant.ok { border-left-color: #10b981; }
        .tenant-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }
        .tenant-name { font-size: 20px; font-weight: 600; cursor: pointer; }
        .tenant-name:hover { color: #3b82f6; }
        .tenant-url { color: var(--text-secondary); font-size: 12px; margin-top: 4px; }
        .status-badge {
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }
        .badge-error { background: #ef4444; color: white; }
        .badge-warning { background: #f59e0b; color: white; }
        .badge-ok { background: #10b981; color: white; }
        .hosts {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 10px;
            margin-top: 15px;
        }
        .host {
            background: var(--bg-tertiary);
            padding: 12px;
            border-radius: 6px;
            border: 1px solid var(--border-color);
            cursor: pointer;
            transition: transform 0.2s, border-color 0.2s;
            display: block;
        }
        .host.hidden {
            display: none;
        }
        .host:hover {
            transform: translateY(-2px);
            border-color: #3b82f6;
        }
        .host.error { 
            border-color: #ef4444;
        }
        [data-theme="dark"] .host.error {
            background: #1e1518;
        }
        [data-theme="light"] .host.error {
            background: #fef2f2;
        }
        .host-name { font-weight: 500; margin-bottom: 4px; }
        .host-status { 
            font-size: 12px; 
            color: var(--text-secondary); 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
        }
        .host-status .os-info {
            font-size: 11px;
            color: var(--text-secondary);
            margin-left: 8px;
            white-space: nowrap;
        }
        .host-status.down { color: #ef4444; }
        .host-details { font-size: 11px; color: var(--text-secondary); margin-top: 4px; }
        .host-issues { 
            font-size: 11px; 
            color: #ef4444; 
            margin-top: 6px; 
            padding-top: 6px;
            border-top: 1px solid var(--border-color);
            font-weight: 500;
        }
        .host-issues.warning { color: #f59e0b; }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 15px;
            margin-bottom: 10px; 
        }
        .stat-card {
            background: var(--bg-secondary);
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        .stat-value { font-size: 32px; font-weight: 700; margin-bottom: 4px; }
        .stat-label { color: var(--text-secondary); font-size: 12px; text-transform: uppercase; }
        .error-msg { color: #ef4444; font-size: 14px; }
        .refresh-info {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            margin-bottom: 20px;
            border-bottom: 1px solid var(--border-color);
            font-size: 13px;
            color: var(--text-secondary);
        }
        .refresh-interval {
             color: #3b82f6;
        }
        .refresh { 
            color: #3b82f6; 
            text-decoration: none;
            font-size: 14px;
            padding: 8px 16px;
            border: 1px solid #3b82f6;
            border-radius: 4px;
            display: inline-block;
        }
        .refresh:hover { background: #1e3a8a; }
        
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);
            backdrop-filter: blur(4px);
        }
        .modal.show { display: flex; align-items: center; justify-content: center; }
        .modal-content {
            background: var(--bg-secondary);
            border-radius: 12px;
            padding: 30px;
            max-width: 600px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
            border: 1px solid var(--border-color);
        }
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid var(--border-color);
        }
        .modal-title { font-size: 24px; font-weight: 600; }
        .modal-close {
            background: none;
            border: none;
            font-size: 28px;
            cursor: pointer;
            color: var(--text-secondary);
            padding: 0;
            width: 32px;
            height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 4px;
        }
        .modal-close:hover { background: var(--border-color); }
        .detail-row {
            display: flex;
            justify-content: space-between;
            padding: 12px 0;
            border-bottom: 1px solid var(--border-color);
        }
        .detail-row:last-child { border-bottom: none; }
        .detail-label { color: var(--text-secondary); font-weight: 500; }
        .detail-value { color: var(--text-primary); }
        .status-indicator {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }
        .status-indicator.ok { background: #10b981; color: white; }
        .status-indicator.warning { background: #f59e0b; color: white; }
        .status-indicator.error { background: #ef4444; color: white; }
        
        /* DYNAMIC STATUS COLORS FOR ISSUES CARD */
        .issue-card-error { 
            background: #ef4444; 
            color: white; 
            border: 1px solid #b91c1c; 
        }
        .issue-card-warn { 
            background: #f59e0b; 
            color: white; 
            border: 1px solid #d97706; 
        }
        .issue-card-ok { 
            background: #10b981; 
            color: white; 
            border: 1px solid #047857; 
        }
        /* END DYNAMIC STATUS COLORS */


        /* -------------------------------------------------------------------------- */
        /* MOBILE OPTIMIZATIONS                                                    */
        /* -------------------------------------------------------------------------- */
        @media (max-width: 768px) {
            
            body {
                padding: 10px;
            }

            .header {
                flex-direction: column;
                align-items: flex-start;
                padding: 15px;
            }

            .controls {
                margin-top: 15px;
                width: 100%;
                flex-direction: column; 
                align-items: stretch;
            }

            .sort-dropdown {
                margin-top: 8px;
                margin-right: 0;
                font-size: 16px; 
            }
            
            .theme-toggle {
                 font-size: 16px; 
            }
            
            .user-logout-group {
                display: flex;
                width: 100%;
                justify-content: space-between;
                margin-bottom: 8px; 
            }

            .user-info {
                flex-grow: 1;
                margin-right: 8px;
                text-align: center;
            }
            .logout-btn {
                flex-shrink: 0;
            }


            .stats {
                grid-template-columns: 1fr 1fr; 
                gap: 10px;
                margin-bottom: 15px;
            }
            .stat-card {
                padding: 12px;
            }
            .stat-value {
                font-size: 28px;
            }
            .stat-label {
                font-size: 11px;
            }
            
            .tenant-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 10px;
            }
            .tenant-name {
                font-size: 22px;
            }

            .hosts {
                grid-template-columns: 1fr;
                gap: 10px;
            }
            
            .host {
                padding: 15px;
            }
            .host-name { 
                font-size: 16px;
            }
            
            .refresh-info {
                flex-direction: column;
                align-items: center;
                gap: 5px;
                font-size: 12px;
            }
            
            .host-status { 
                flex-direction: column;
                align-items: flex-start;
                gap: 2px;
                font-size: 12px;
            }
            .host-status .os-info {
                margin-left: 0;
                white-space: normal;
                text-align: left;
            }

            @media (max-width: 400px) {
                .stats {
                    grid-template-columns: 1fr;
                }
            }
        }

        /* === Fix unreadable grey text on colored cards (dark + light themes) === */

        /* General: ensure colored cards use white text */
        .issue-card-error,
        .issue-card-warn,
        .issue-card-ok {
        color: #ffffff;
        }

        .issue-card-error .stat-value,
        .issue-card-error .stat-label,
        .issue-card-warn .stat-value,
        .issue-card-warn .stat-label,
        .issue-card-ok .stat-value,
        .issue-card-ok .stat-label {
        color: #ffffff !important;
        }

        /* Slight text shadow for better readability */
        .issue-card-error .stat-value,
        .issue-card-warn .stat-value,
        .issue-card-ok .stat-value {
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);
        }

        /* ---------- DARK THEME ---------- */
        [data-theme="dark"] .host.error {
        background: #3a1a1c; /* slightly brighter red background */
        color: #ffffff;
        }
        [data-theme="dark"] .host.error .host-name,
        [data-theme="dark"] .host.error .host-status,
        [data-theme="dark"] .host.error .host-status .os-info,
        [data-theme="dark"] .host.error .host-details,
        [data-theme="dark"] .host.error .host-issues {
        color: #ffffff !important;
        }

        [data-theme="dark"] .host.warning {
        background: #3b2a0a; /* warmer dark yellow tone */
        color: #ffffff;
        }
        [data-theme="dark"] .host.warning .host-name,
        [data-theme="dark"] .host.warning .host-status,
        [data-theme="dark"] .host.warning .host-details {
        color: #ffffff !important;
        }

        [data-theme="dark"] .host.ok {
        background: #11321e; /* darker green background */
        color: #ffffff;
        }

        /* ---------- LIGHT THEME ---------- */
        [data-theme="light"] .issue-card-error {
        background: #dc2626; /* solid red */
        border-color: #b91c1c;
        color: #ffffff;
        }
        [data-theme="light"] .issue-card-warn {
        background: #f59e0b;
        border-color: #d97706;
        color: #ffffff;
        }
        [data-theme="light"] .issue-card-ok {
        background: #10b981;
        border-color: #047857;
        color: #ffffff;
        }

        [data-theme="light"] .host.error {
        background: #fee2e2; /* lighter red */
        color: #7f1d1d;
        }
        [data-theme="light"] .host.warning {
        background: #fef3c7; /* soft yellow */
        color: #78350f;
        }
        [data-theme="light"] .host.ok {
        background: #ecfdf5; /* pale green */
        color: #064e3b;
        }

        /* Prevent grey text override in colored hosts */
        [data-theme="light"] .host.error .host-name,
        [data-theme="light"] .host.error .host-status,
        [data-theme="light"] .host.warning .host-name,
        [data-theme="light"] .host.warning .host-status,
        [data-theme="light"] .host.ok .host-name,
        [data-theme="light"] .host.ok .host-status {
        color: inherit !important;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-content">
            <h1>🖥️ MMonit Hub</h1>
            <div class="subtitle">Multi-tenant monitoring dashboard</div>
        </div>
        <div class="controls">
            <div class="user-logout-group">
                <span class="user-info">👤 USERNAME_PLACEHOLDER</span>
                <button class="logout-btn" id="logoutBtn">Logout / Change User</button>
            </div>
            <input type="text" id="hostFilter" placeholder="Filter hosts..." style="padding: 8px; border-radius: 4px; border: 1px solid var(--border-color); background: var(--bg-tertiary); color: var(--text-primary); font-size: 14px; flex-grow: 1;">
            <select class="sort-dropdown" id="sortSelect">
                <option value="issues-first">Issues First</option>
                <option value="name">Sort by Name</option>
                <option value="hosts">Sort by Host Count</option>
                <option value="cpu">Sort by CPU Usage</option>
                <option value="memory">Sort by Memory Usage</option>
                <option value="disk">Sort by Disk Usage</option>
                <option value="os">Sort by OS</option>
                <option value="os-version">Sort by OS Version</option>
                <option value="os-update-needed">Needs OS Review</option>
            </select>
            <button class="theme-toggle" id="themeToggle">
                <span id="themeIcon">🌙</span>
            </button>
        </div>
    </div>
    
    <div class="stats">
        <div class="stat-card">
            <div class="stat-value" id="total-tenants">-</div>
            <div class="stat-label">Total Tenants</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" id="total-hosts">-</div>
            <div class="stat-label">Total Hosts</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" id="total-services">-</div>
            <div class="stat-label">Total Services</div>
        </div>
        <div class="stat-card" id="issues-card">
            <div class="stat-value" id="issues">-</div>
            <div class="stat-label">Issues Detected</div>
        </div>
    </div>

    <div class="stats" id="os-stats-container">
    </div>
    <div class="refresh-info">
        <span id="last-update">Last Updated: N/A</span>
        <span id="refresh-interval-display"></span>
    </div>
    
    <div id="tenants"></div>
    
    <div style="text-align: center; margin-top: 20px;">
        <a href="/" class="refresh">🔄 Refresh</a>
    </div>
    
    <div id="hostModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <div class="modal-title" id="modalTitle"></div>
                <button class="modal-close" id="modalClose">&times;</button>
            </div>
            <div id="modalBody"></div>
        </div>
    </div>
    
    <script>
        let tenantsData = [];
        
        // --- UTILITY FUNCTIONS ---
        
        // Helper for numeric version comparison (e.g., "14.1.2" vs "14.2.0")
        function compareVersions(v1, v2) {
            v1 = v1 || '0';
            v2 = v2 || '0';
            // Remove build/patch suffixes for primary comparison (e.g., "-RELEASE-p3")
            const cleanV1 = v1.split('-')[0].split('.');
            const cleanV2 = v2.split('-')[0].split('.');
            
            for (let i = 0; i < Math.max(cleanV1.length, cleanV2.length); i++) {
                const num1 = parseInt(cleanV1[i]) || 0;
                const num2 = parseInt(cleanV2[i]) || 0;
                
                if (num1 < num2) return -1;
                if (num1 > num2) return 1;
            }
            return 0;
        }

        // FIX: Reliable Basic Auth logout trick using fetch with invalid credentials
        document.getElementById('logoutBtn').addEventListener('click', () => {
            const currentUrl = window.location.href.split('?')[0].split('#')[0];
            const baseUrl = currentUrl.split('//')[0] + '//' + currentUrl.split('//')[1].split('/')[0];

            fetch(currentUrl, {
                headers: {
                    'Authorization': 'Basic ' + btoa('logout:invalid')
                }
            }).then(() => {
                window.location.href = baseUrl;
            }).catch(() => {
                 window.location.href = baseUrl;
            });
        });
        
        function displayTimeInfo(lastFetchUnix, refreshSeconds) {
            const lastUpdateElement = document.getElementById('last-update');
            const intervalElement = document.getElementById('refresh-interval-display');
            
            if (lastFetchUnix) {
                const date = new Date(lastFetchUnix * 1000);
                lastUpdateElement.textContent = 'Last Updated: ' + date.toLocaleTimeString(); 
            } else {
                 lastUpdateElement.textContent = 'Last Updated: N/A';
            }
            
            if (refreshSeconds > 0) {
                 intervalElement.innerHTML = `Auto-refresh: <span class="refresh-interval">${refreshSeconds}s</span>`; 
            } else {
                 intervalElement.textContent = 'Auto-refresh: Disabled';
            }
        }
        
        // --- RENDER OS STATS FUNCTION ---
        function renderOSStats(allHosts) {
            const osCounts = allHosts.reduce((acc, host) => {
                if (host.os_name && host.os_name !== 'OS N/A') {
                    const osKey = host.os_name; // Use only OS name for grouping
                    acc[osKey] = (acc[osKey] || 0) + 1;
                }
                return acc;
            }, {});

            const sortedOS = Object.entries(osCounts).sort(([, countA], [, countB]) => countB - countA);

            const container = document.getElementById('os-stats-container');
            container.innerHTML = '';
            
            if (sortedOS.length === 0) {
                container.style.display = 'none';
                return;
            } else {
                container.style.display = 'grid';
            }

            sortedOS.slice(0, 4).forEach(([osKey, count]) => {
                const statCard = document.createElement('div');
                statCard.className = 'stat-card';
                statCard.innerHTML = `
                    <div class="stat-value">${count}</div>
                    <div class="stat-label">${osKey.toUpperCase()} HOSTS</div>
                `;
                container.appendChild(statCard);
            });
        }
        // --- END: RENDER OS STATS FUNCTION ---
        
        // Modal functions
        function showHostDetails(host, tenantUrl) {
            const modal = document.getElementById('hostModal');
            const modalTitle = document.getElementById('modalTitle');
            const modalBody = document.getElementById('modalBody');
            
            const statusClass = host.led === 0 ? 'error' : (host.led === 1 ? 'warning' : 'ok');
            const statusText = host.led === 0 ? 'Error' : (host.led === 1 ? 'Warning' : 'OK');
            
            let filesystemsHtml = '';
            if (host.filesystems && host.filesystems.length > 0) {
                filesystemsHtml = '<div class="detail-row"><div class="detail-label">Filesystems</div><div class="detail-value">';
                host.filesystems.forEach(fs => {
                    const usageClass = fs.usage_percent > 90 ? 'error' : (fs.usage_percent > 80 ? 'warning' : 'ok');
                    filesystemsHtml += `
                        <div style="margin-bottom: 8px;">
                            <div><strong>${fs.name}</strong></div>
                            <div>
                                <span class="status-indicator ${usageClass}">${fs.usage_percent.toFixed(1)}%</span>
                                ${fs.usage_mb !== null ? ` ${(fs.usage_mb / 1024).toFixed(1)} GB / ${(fs.total_mb / 1024).toFixed(1)} GB` : ''}
                            </div>
                        </div>
                    `;
                });
                filesystemsHtml += '</div></div>';
            }
            
            let issuesDetailsHtml = '';
            if (host.issues && host.issues.length > 0) {
                issuesDetailsHtml = '<div class="detail-row"><div class="detail-label">Service Issues</div><div class="detail-value">';
                host.issues.forEach(issue => {
                    const issueClass = issue.led === 0 ? 'error' : 'warning';
                    issuesDetailsHtml += `
                        <div style="margin-bottom: 8px;">
                            <div><strong>${issue.name}</strong> (${issue.type})</div>
                            <div>
                                <span class="status-indicator ${issueClass}">${issue.status}</span>
                            </div>
                        </div>
                    `;
                });
                issuesDetailsHtml += '</div></div>';
            }
            
            modalTitle.textContent = host.hostname;
            modalBody.innerHTML = `
                <div class="detail-row">
                    <div class="detail-label">Status</div>
                    <div class="detail-value">
                        <span class="status-indicator ${statusClass}">${statusText}</span>
                    </div>
                </div>
                ${issuesDetailsHtml}
                <div class="detail-row">
                    <div class="detail-label">Operating System</div>
                    <div class="detail-value">${host.os_name} (${host.os_release || 'N/A'})</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label">CPU Usage</div>
                    <div class="detail-value">${host.cpu}%</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label">Memory Usage</div>
                    <div class="detail-value">${host.mem}%</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label">Events</div>
                    <div class="detail-value">${host.events}</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label">Heartbeat</div>
                    <div class="detail-value">${host.heartbeat ? '✓ Active' : '✗ Inactive'}</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label">Host ID</div>
                    <div class="detail-value">${host.id}</div>
                </div>
                ${filesystemsHtml}
                <div style="margin-top: 20px; text-align: center;">
                    <a href="${tenantUrl}/admin/hosts/get?id=${host.id}" target="_blank" class="refresh">
                        View in MMonit →
                    </a>
                </div>
            `;
            
            modal.classList.add('show');
        }
        
        function closeModal() {
            document.getElementById('hostModal').classList.remove('show');
        }
        
        document.getElementById('modalClose').addEventListener('click', closeModal);
        document.getElementById('hostModal').addEventListener('click', (e) => {
            if (e.target.id === 'hostModal') closeModal();
        });
        
        function initTheme() {
            const savedTheme = localStorage.getItem('theme');
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            const theme = savedTheme || (prefersDark ? 'dark' : 'light');
            setTheme(theme);
        }
        
        function setTheme(theme) {
            document.documentElement.setAttribute('data-theme', theme);
            document.getElementById('themeIcon').textContent = theme === 'dark' ? '☀️' : '🌙';
            localStorage.setItem('theme', theme);
        }
        
        document.getElementById('themeToggle').addEventListener('click', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            setTheme(currentTheme === 'dark' ? 'light' : 'dark');
        });
        
        function sortTenants(data, sortBy) {
            const sorted = [...data];
            
            switch(sortBy) {
                case 'issues-first':
                    return sorted.sort((a, b) => {
                        const aIssues = a.error ? 10000 : (a.hosts || []).filter(h => h.led !== 2).length;
                        const bIssues = b.error ? 10000 : (b.hosts || []).filter(h => b.led !== 2).length;
                        
                        if (aIssues !== bIssues) {
                           return bIssues - aIssues;
                        }
                        
                        const aHostsTotal = (a.hosts || []).length;
                        const bHostsTotal = (b.hosts || []).length;
                        return bHostsTotal - aHostsTotal; // Tiebreaker
                    });
                case 'name':
                    return sorted.sort((a, b) => a.tenant.localeCompare(b.tenant));
                case 'hosts':
                    return sorted.sort((a, b) => {
                        const aHosts = (a.hosts || []).length;
                        const bHosts = (b.hosts || []).length;
                        return bHosts - aHosts;
                    });
                case 'cpu':
                    return sorted.sort((a, b) => {
                        const aAvg = (a.hosts || []).reduce((sum, h) => sum + (h.cpu || 0), 0) / ((a.hosts || []).length || 1);
                        const bAvg = (b.hosts || []).reduce((sum, h) => sum + (h.cpu || 0), 0) / ((b.hosts || []).length || 1);
                        return bAvg - aAvg;
                    });
                case 'memory':
                    return sorted.sort((a, b) => {
                        const aAvg = (a.hosts || []).reduce((sum, h) => sum + (h.mem || 0), 0) / ((a.hosts || []).length || 1);
                        const bAvg = (b.hosts || []).reduce((sum, h) => sum + (h.mem || 0), 0) / ((b.hosts || []).length || 1);
                        return bAvg - aAvg;
                    });
                case 'disk':
                    return sorted.sort((a, b) => {
                        const getAvgMaxDisk = (tenant) => {
                            const diskUsages = (tenant.hosts || [])
                                .map(h => Math.max(...(h.filesystems || []).map(fs => fs.usage_percent || 0), 0));
                            
                            return diskUsages.length > 0
                                ? diskUsages.reduce((sum, usage) => sum + usage, 0) / diskUsages.length
                                : 0;
                        };

                        const aAvgMaxDisk = a.error ? -1 : getAvgMaxDisk(a);
                        const bAvgMaxDisk = b.error ? -1 : getAvgMaxDisk(b);
                        
                        return bAvgMaxDisk - aAvgMaxDisk;
                    });
                case 'os': // Sort by OS Name (alphabetical)
                    return sorted.sort((a, b) => {
                        const aOS = (a.hosts[0] && a.hosts[0].os_name) || 'zzzzzz';
                        const bOS = (b.hosts[0] && b.hosts[0].os_name) || 'zzzzzz';
                        return aOS.localeCompare(bOS); 
                    });
                case 'os-version': // Sort by OS Version (numeric comparison, Ascending: oldest first)
                    return sorted.sort((a, b) => {
                        // Find the OLDEST version in each tenant group for sorting
                        const aHostVersions = (a.hosts || []).map(h => h.os_release || '0');
                        const bHostVersions = (b.hosts || []).map(h => h.os_release || '0');

                        const aOldestVersion = aHostVersions.sort(compareVersions)[0];
                        const bOldestVersion = bHostVersions.sort(compareVersions)[0];
                        
                        return compareVersions(aOldestVersion, bOldestVersion); 
                    });
                case 'os-update-needed': 
                     return sorted.sort((a, b) => {
                        const aNeedsUpdate = (a.hosts || []).some(h => !h.os_release);
                        const bNeedsUpdate = (b.hosts || []).some(h => !b.os_release);
                        
                        if (aNeedsUpdate && !bNeedsUpdate) return -1;
                        if (!aNeedsUpdate && bNeedsUpdate) return 1;
                        
                        const aIssues = a.error ? 1000 : (a.hosts || []).filter(h => h.led !== 2).length;
                        const bIssues = b.error ? 1000 : (b.hosts || []).filter(h => h.led !== 2).length;
                        return bIssues - aIssues;
                    });
                default:
                    return sorted;
            }
        }
        
        function renderTenants(data) {
            const processedTenants = data.tenants; 
        
            const container = document.getElementById('tenants');
            container.innerHTML = '';
            let totalHosts = 0;
            let totalIssues = 0;
            let totalServices = 0; 

            const allHosts = processedTenants.flatMap(tenant => tenant.hosts || []);
            renderOSStats(allHosts); 

            processedTenants.forEach(tenant => { 
                const div = document.createElement('div');
                div.className = 'tenant';
                
                if (tenant.error) {
                    div.classList.add('error');
                    div.innerHTML = `
                        <div class="tenant-header">
                            <div>
                                <div class="tenant-name">${tenant.tenant}</div>
                                <div class="tenant-url">${tenant.url}</div>
                            </div>
                            <span class="status-badge badge-error">ERROR</span>
                        </div>
                        <div class="error-msg">⚠️ ${tenant.error}</div>
                    `;
                } else {
                    const hosts = tenant.hosts || [];
                    const issues = hosts.filter(h => h.led !== 2).length;
                    
                    totalHosts += hosts.length;
                    totalIssues += issues;
                    
                    totalServices += hosts.reduce((sum, h) => sum + (h.service_count || 0), 0);
                    
                    div.classList.add(issues > 0 ? 'issues' : 'ok');
                    
                    let hostsHtml = '';
                    if (hosts.length > 0) {
                        hostsHtml = '<div class="hosts">';
                        hosts.forEach(host => {
                            const isDown = host.led !== 2;
                            const statusIcon = host.led === 0 ? '🔴' : (host.led === 1 ? '🟡' : '🟢');
                            const statusText = host.led === 0 ? 'Error' : (host.led === 1 ? 'Warning' : 'Running');
                            
                            let diskInfo = '';
                            if (host.filesystems && host.filesystems.length > 0) {
                                const maxDisk = host.filesystems.reduce((max, fs) => 
                                    fs.usage_percent > max ? fs.usage_percent : max, 0);
                                diskInfo = ` | Disk: ${maxDisk.toFixed(1)}%`;
                            }
                            
                            let issuesHtml = '';
                            if (host.issues && host.issues.length > 0) {
                                const errorIssues = host.issues.filter(i => i.led === 0);
                                const warningIssues = host.issues.filter(i => i.led === 1);
                                
                                if (errorIssues.length > 0) {
                                    issuesHtml = `<div class="host-issues">⚠️ ${errorIssues.map(i => i.name).join(', ')}</div>`;
                                } else if (warningIssues.length > 0) {
                                    issuesHtml = `<div class="host-issues warning">⚠️ ${warningIssues.map(i => i.name).join(', ')}</div>`;
                                }
                            }
                            
                            const os_name = host.os_name && host.os_name !== 'OS N/A' ? host.os_name : 'OS N/A';
                            const os_release = host.os_release ? host.os_release : '';
                            const os_version_display = os_release ? ` ${os_release}` : '';

                            const hostName = host.hostname || 'Unknown';
                            const filterText = document.getElementById('hostFilter').value.toLowerCase();
                            
                            const hostSearchableText = `${hostName} ${os_name} ${os_release}`.toLowerCase();
                            const isHidden = filterText && !hostSearchableText.includes(filterText) ? 'hidden' : '';

                            hostsHtml += `
                                <div class="host ${isDown ? 'error' : ''} ${isHidden}" onclick='showHostDetails(${JSON.stringify(host)}, "${tenant.url}")'>
                                    <div class="host-name">${hostName}</div>
                                    <div class="host-status ${isDown ? 'down' : ''}">
                                        <span>${statusIcon} ${statusText}</span>
                                        <span class="os-info">${os_name}${os_version_display}</span>
                                    </div>
                                    <div class="host-details">
                                        CPU: ${host.cpu}% | Mem: ${host.mem}%${diskInfo}
                                    </div>
                                    ${issuesHtml}
                                </div>
                            `;
                        });
                        hostsHtml += '</div>';
                    }
                    
                    div.innerHTML = `
                        <div class="tenant-header">
                            <div>
                                <div class="tenant-name" onclick="window.open('${tenant.url}', '_blank')">${tenant.tenant}</div>
                                <div class="tenant-url">${tenant.url}</div>
                            </div>
                            <span class="status-badge ${issues > 0 ? 'badge-warning' : 'badge-ok'}">
                                ${hosts.length} hosts • ${issues} issues
                            </span>
                        </div>
                        ${hostsHtml}
                    `;
                }
                
                container.appendChild(div);
            });
            
            // --- DYNAMIC STATUS CARD FIX ---
            const issuesCard = document.getElementById('issues-card');
            issuesCard.className = 'stat-card'; // Reset classes
            
            if (totalIssues > 0) {
                 // Check if any host has a red (0) led status in its issues list
                 const hasError = allHosts.some(host => (host.issues || []).some(issue => issue.led === 0));
                 
                 if (hasError) {
                     issuesCard.classList.add('issue-card-error');
                 } else {
                     issuesCard.classList.add('issue-card-warn');
                 }
            } else {
                 issuesCard.classList.add('issue-card-ok');
            }
            // --- END DYNAMIC STATUS CARD FIX ---

            
            document.getElementById('total-tenants').textContent = data.tenants.length; 
            document.getElementById('total-hosts').textContent = totalHosts;
            document.getElementById('total-services').textContent = totalServices;
            document.getElementById('issues').textContent = totalIssues;
            
            displayTimeInfo(data.last_fetch_time, data.refresh_interval); 
            
            tenantsData = processedTenants; 
            const currentSort = document.getElementById('sortSelect').value;
            const sorted = sortTenants(processedTenants, currentSort);
            renderTenantsOnly(sorted); 
        }

        // Helper function to re-render data content only (used by sort/auto-refresh)
        function renderTenantsOnly(data) {
             const container = document.getElementById('tenants');
            container.innerHTML = '';
            let totalHosts = 0;
            let totalIssues = 0;
            let totalServices = 0; 
            
            const allHosts = data.flatMap(tenant => tenant.hosts || []);
            renderOSStats(allHosts);
            
            const filterText = document.getElementById('hostFilter').value.toLowerCase();
            const selectedSort = document.getElementById('sortSelect').value;
            
            data.forEach(tenant => {
                const div = document.createElement('div');
                div.className = 'tenant';
                
                if (tenant.error) {
                    div.classList.add('error');
                    div.innerHTML = `
                        <div class="tenant-header">
                            <div>
                                <div class="tenant-name">${tenant.tenant}</div>
                                <div class="tenant-url">${tenant.url}</div>
                            </div>
                            <span class="status-badge badge-error">ERROR</span>
                        </div>
                        <div class="error-msg">⚠️ ${tenant.error}</div>
                    `;
                } else {
                    const hosts = tenant.hosts || [];
                    const issues = hosts.filter(h => h.led !== 2).length;
                    
                    totalHosts += hosts.length;
                    totalIssues += issues;
                    totalServices += hosts.reduce((sum, h) => sum + (h.service_count || 0), 0);
                    
                    div.classList.add(issues > 0 ? 'issues' : 'ok');
                    
                    let hostsHtml = '';
                    if (hosts.length > 0) {
                        hostsHtml = '<div class="hosts">';
                        hosts.forEach(host => {
                            const isDown = host.led !== 2;
                            const statusIcon = host.led === 0 ? '🔴' : (host.led === 1 ? '🟡' : '🟢');
                            const statusText = host.led === 0 ? 'Error' : (host.led === 1 ? 'Warning' : 'Running');
                            
                            let diskInfo = '';
                            if (host.filesystems && host.filesystems.length > 0) {
                                const maxDisk = host.filesystems.reduce((max, fs) => 
                                    fs.usage_percent > max ? fs.usage_percent : max, 0);
                                diskInfo = ` | Disk: ${maxDisk.toFixed(1)}%`;
                            }
                            
                            let issuesHtml = '';
                            if (host.issues && host.issues.length > 0) {
                                const errorIssues = host.issues.filter(i => i.led === 0);
                                const warningIssues = host.issues.filter(i => i.led === 1);
                                
                                if (errorIssues.length > 0) {
                                    issuesHtml = `<div class="host-issues">⚠️ ${errorIssues.map(i => i.name).join(', ')}</div>`;
                                } else if (warningIssues.length > 0) {
                                    issuesHtml = `<div class="host-issues warning">⚠️ ${warningIssues.map(i => i.name).join(', ')}</div>`;
                                }
                            }
                            
                            const os_name = host.os_name && host.os_name !== 'OS N/A' ? host.os_name : 'OS N/A';
                            const os_release = host.os_release ? host.os_release : '';
                            const os_version_display = os_release ? ` ${os_release}` : '';

                            const hostName = host.hostname || 'Unknown';
                            
                            // --- ENHANCED FILTERING LOGIC ---
                            const hostSearchableText = `${hostName} ${os_name} ${os_release}`.toLowerCase();
                            let isHidden = filterText && !hostSearchableText.includes(filterText) ? 'hidden' : '';
                            // --- END ENHANCED FILTERING LOGIC ---

                            // Apply OS Update filter
                            if (selectedSort === 'os-update-needed' && !isHidden) {
                                if (host.os_release) { // Hide if release is present
                                    isHidden = 'hidden';
                                } else { // Show if release is missing/needs review
                                    isHidden = '';
                                }
                            }

                            // FIX: Corrected onclick handler to pass host data and tenant URL correctly
                            hostsHtml += `
                                <div class="host ${isDown ? 'error' : ''} ${isHidden}" onclick='showHostDetails(${JSON.stringify(host)}, "${tenant.url}")'>
                                    <div class="host-name">${hostName}</div>
                                    <div class="host-status ${isDown ? 'down' : ''}">
                                        <span>${statusIcon} ${statusText}</span>
                                        <span class="os-info">${os_name}${os_version_display}</span>
                                    </div>
                                    <div class="host-details">
                                        CPU: ${host.cpu}% | Mem: ${host.mem}%${diskInfo}
                                    </div>
                                    ${issuesHtml}
                                </div>
                            `;
                        });
                        hostsHtml += '</div>';
                    }
                    
                    div.innerHTML = `
                        <div class="tenant-header">
                            <div>
                                <div class="tenant-name" onclick="window.open('${tenant.url}', '_blank')">${tenant.tenant}</div>
                                <div class="tenant-url">${tenant.url}</div>
                            </div>
                            <span class="status-badge ${issues > 0 ? 'badge-warning' : 'badge-ok'}">
                                ${hosts.length} hosts • ${issues} issues
                            </span>
                        </div>
                        ${hostsHtml}
                    `;
                }
                
                container.appendChild(div);
            });
            
            // --- DYNAMIC STATUS CARD FIX ---
            const issuesCard = document.getElementById('issues-card');
            issuesCard.className = 'stat-card'; // Reset classes
            
            if (totalIssues > 0) {
                 const hasError = allHosts.some(host => (host.issues || []).some(issue => issue.led === 0));
                 
                 if (hasError) {
                     issuesCard.classList.add('issue-card-error');
                 } else {
                     issuesCard.classList.add('issue-card-warn');
                 }
            } else {
                 issuesCard.classList.add('issue-card-ok');
            }
            // --- END DYNAMIC STATUS CARD FIX ---

            // Update counters manually on re-render
            document.getElementById('total-hosts').textContent = totalHosts;
            document.getElementById('total-services').textContent = totalServices;
            document.getElementById('issues').textContent = totalIssues;
        }

        // Attach event listeners for sort and filter
        document.getElementById('sortSelect').addEventListener('change', (e) => {
            const sorted = sortTenants(tenantsData, e.target.value);
            renderTenantsOnly(sorted);
        });
        
        document.getElementById('hostFilter').addEventListener('input', (e) => {
            const currentSort = document.getElementById('sortSelect').value;
            const sorted = sortTenants(tenantsData, currentSort);
            renderTenantsOnly(sorted);
        });

        
        fetch('/api/data')
            .then(r => r.json())
            .then(data => {
                const username = document.querySelector('.user-info').textContent;
                document.querySelector('.user-info').textContent = username.replace('USERNAME_PLACEHOLDER', data.username || 'N/A');
                
                renderTenants(data);
            })
            .catch(err => {
                document.getElementById('tenants').innerHTML = 
                    '<div class="tenant error"><div class="error-msg">Failed to load data: ' + err + '</div></div>';
            });
        
        initTheme();
        
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            if (!localStorage.getItem('theme')) {
                setTheme(e.matches ? 'dark' : 'light');
            }
        });
        
        // Auto-refresh functionality
        const AUTO_REFRESH_SECONDS = AUTO_REFRESH_INTERVAL_PLACEHOLDER;
        if (AUTO_REFRESH_SECONDS > 0) {
            setInterval(() => {
                fetch('/api/data')
                    .then(r => r.json())
                    .then(data => {
                        const currentSort = document.getElementById('sortSelect').value;
                        
                        displayTimeInfo(data.last_fetch_time, data.refresh_interval);
                        tenantsData = data.tenants;
                        const sorted = sortTenants(data.tenants, currentSort);
                        renderTenantsOnly(sorted);
                    })
                    .catch(err => console.error('Auto-refresh failed:', err));
            }, AUTO_REFRESH_SECONDS * 1000);
        }
    </script>
</body>
</html>'''

# --- HANDLER CLASS ---

class MMonitHandler(BaseHTTPRequestHandler):
    config = None
    
    def log_message(self, format, *args):
        if args[0].split(' ')[0] in ['"GET', '"POST'] and '401' in args[0]:
            return
        if 'favicon.ico' in args[0]:
            return
        
        print(f"{self.address_string()} - {args[0]}")
            
    def do_AUTH_response(self):
        """Sends a 401 response prompting for Basic Auth"""
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header('WWW-Authenticate', 'Basic realm="MMonit Hub"')
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<h1>Authentication Required</h1>')

    def require_auth_user(self):
        """
        Check for Basic Auth header and validate credentials.
        Returns username or None.
        """
        if 'users' not in self.config or not self.config['users']:
            return 'anonymous'
        
        auth_header = self.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Basic '):
            return None
        
        try:
            encoded_credentials = auth_header.split(' ')[1]
            decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
            username, password = decoded_credentials.split(':', 1)
        except Exception:
            return None

        for user in self.config['users']:
            if user['username'] == username:
                if verify_password(password, user['password']):
                    return username
        
        return None
    
    def get_user_tenants(self, username):
        """Get list of tenants user can access"""
        if username == 'anonymous' or 'users' not in self.config:
            return ['*']
        
        for user in self.config['users']:
            if user['username'] == username:
                return user.get('tenants', [])
        
        return []
        
    def do_GET(self):
        global LAST_FETCH_TIME
        
        try: 
            parsed_path = urlparse(self.path)
            
            # --- Basic Auth Enforcement ---
            username = self.require_auth_user()
            
            if not username:
                self.do_AUTH_response()
                return
            # --- End Auth Enforcement ---
            
            if parsed_path.path == '/':
                self.send_response(HTTPStatus.OK)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                
                html = HTML_CONTENT.replace('AUTO_REFRESH_INTERVAL_PLACEHOLDER', str(AUTO_REFRESH_INTERVAL))
                html = html.replace('USERNAME_PLACEHOLDER', username) 
                
                self.wfile.write(html.encode('utf-8'))
                
            elif parsed_path.path == '/api/data':
                self.send_response(HTTPStatus.OK)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                
                allowed_tenants = self.get_user_tenants(username)
                
                # Fetch data
                tenant_data = query_mmonit_data(self.config['instances'], allowed_tenants)
                
                # Update fetch time BEFORE sending response
                LAST_FETCH_TIME = datetime.now(timezone.utc)
                
                # Prepare combined JSON response object
                response_data = {
                    'username': username,
                    'tenants': tenant_data,
                    'last_fetch_time': int(LAST_FETCH_TIME.timestamp()), 
                    'refresh_interval': AUTO_REFRESH_INTERVAL
                }

                self.wfile.write(json.dumps(response_data, ensure_ascii=False).encode('utf-8'))
                
            else:
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()
                
        # Handle connection errors gracefully
        except (ConnectionResetError, BrokenPipeError, socket.error) as e:
            if isinstance(e, socket.error) and 'Broken pipe' in str(e):
                 self.log_message("Client disconnected during response write (BrokenPipeError).")
            elif isinstance(e, ConnectionResetError):
                 self.log_message("Client disconnected during response write (ConnectionResetError).")
            else:
                 self.log_error("Connection error during do_GET: %s", str(e))
        except Exception as e:
            self.log_error("Unexpected error during do_GET: %s", str(e))
            
    # POST requests are not used in this Basic Auth version.
    def do_POST(self):
        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

# --- MAIN FUNCTION ---

def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--hash-password':
        import getpass
        password = getpass.getpass('Enter password to hash: ')
        password_confirm = getpass.getpass('Confirm password: ')
        
        if password != password_confirm:
            print("Error: Passwords do not match")
            sys.exit(1)
        
        hashed = hash_password(password)
        print(f"\nHashed password: {hashed}")
        print("\nAdd this to your config file in the user's password field.")
        sys.exit(0)
    
    config_path = sys.argv[1] if len(sys.argv) > 1 else CONFIG_FILE
    
    config = load_config(config_path)
    port = config.get('port', 8080)
    
    MMonitHandler.config = config
    
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    server = HTTPServer(('', port), MMonitHandler)
    print(f'MMonit Hub starting...')
    print(f'Config: {config_path}')
    print(f'Monitoring {len(config["instances"])} tenant(s)')
    if 'users' in config and config['users']:
        print(f'Authentication: Basic Auth Enabled ({len(config["users"])} user(s))')
    else:
        print(f'Authentication: Disabled (no users configured)')
    print(f'Dashboard: http://localhost:{port}')
    print('Press Ctrl+C to stop\n')
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down...')
        server.shutdown()

if __name__ == '__main__':
    main()