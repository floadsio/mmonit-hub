#!/usr/bin/env python3
"""
MMonit Hub - Multi-tenant monitoring dashboard
"""

import json
import requests
import sys
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from pathlib import Path

# Default config file location
CONFIG_FILE = 'mmonit-hub.conf'

# Auto-refresh interval in seconds (0 = disabled)
AUTO_REFRESH_INTERVAL = 30

def load_config(config_path):
    """Load configuration from JSON file"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            # Set auto_refresh from config or use default
            global AUTO_REFRESH_INTERVAL
            AUTO_REFRESH_INTERVAL = config.get('auto_refresh_seconds', AUTO_REFRESH_INTERVAL)
            return config
    except FileNotFoundError:
        print(f"Error: Config file '{config_path}' not found!")
        print(f"\nCreate a config file with this format:")
        print(json.dumps({
            "port": 8080,
            "auto_refresh_seconds": 30,
            "instances": [
                {
                    "name": "tenant1",
                    "url": "https://mmonit1.example.com:8080",
                    "username": "admin",
                    "password": "password1"
                }
            ]
        }, indent=2))
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}")
        sys.exit(1)

def query_mmonit_data(instances):
    """Aggregate data from all MMonit instances"""
    result = []
    
    for instance in instances:
        name = instance['name']
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
                    'hosts': []
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
                
                # Step 4: Fetch detailed info for each host to get disk space
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
                            # Extract filesystem info from services
                            filesystems = []
                            issues = []
                            services = detail_data.get('records', {}).get('host', {}).get('services', [])
                            for service in services:
                                # Track services with issues
                                if service.get('led') in [0, 1]:  # red or yellow
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
                    except Exception as e:
                        print(f"Failed to get details for host {host.get('hostname')}: {e}")
                        host['filesystems'] = []
                        host['issues'] = []
                
                # Convert to our format with hosts array
                result.append({
                    'tenant': name,
                    'url': url,
                    'hosts': hosts
                })
            else:
                result.append({
                    'tenant': name,
                    'url': url,
                    'error': f'API error: HTTP {response.status_code}',
                    'hosts': []
                })
                
        except requests.exceptions.Timeout:
            result.append({
                'tenant': name,
                'url': url,
                'error': 'Connection timeout',
                'hosts': []
            })
        except requests.exceptions.ConnectionError:
            result.append({
                'tenant': name,
                'url': url,
                'error': 'Connection failed',
                'hosts': []
            })
        except Exception as e:
            result.append({
                'tenant': name,
                'url': url,
                'error': str(e),
                'hosts': []
            })
    
    return result

HTML_CONTENT = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
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
        }
        .header-content h1 { font-size: 24px; margin-bottom: 8px; }
        .subtitle { color: var(--text-secondary); font-size: 14px; }
        
        .controls {
            display: flex;
            gap: 10px;
            align-items: center;
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
        .host-status { font-size: 12px; color: var(--text-secondary); }
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
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
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
    </style>
</head>
<body>
    <div class="header">
        <div class="header-content">
            <h1>🖥️ MMonit Hub</h1>
            <div class="subtitle">Multi-tenant monitoring dashboard</div>
        </div>
        <div class="controls">
            <select class="sort-dropdown" id="sortSelect">
                <option value="issues-first">Issues First</option>
                <option value="name">Sort by Name</option>
                <option value="hosts">Sort by Host Count</option>
                <option value="cpu">Sort by CPU Usage</option>
                <option value="memory">Sort by Memory Usage</option>
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
            <div class="stat-value" id="issues">-</div>
            <div class="stat-label">Issues Detected</div>
        </div>
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
                    <div class="detail-label">Message</div>
                    <div class="detail-value">${host.status || 'N/A'}</div>
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
                        const aIssues = a.error ? 1000 : (a.hosts || []).filter(h => h.led !== 2).length;
                        const bIssues = b.error ? 1000 : (b.hosts || []).filter(h => h.led !== 2).length;
                        return bIssues - aIssues;
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
                default:
                    return sorted;
            }
        }
        
        function renderTenants(data) {
            const container = document.getElementById('tenants');
            container.innerHTML = '';
            let totalHosts = 0;
            let totalIssues = 0;
            
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
                    // MMonit uses 'led' field: 0=red(error), 1=yellow(warning), 2=green(ok)
                    const issues = hosts.filter(h => h.led !== 2).length;
                    totalHosts += hosts.length;
                    totalIssues += issues;
                    
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
                            
                            hostsHtml += `
                                <div class="host ${isDown ? 'error' : ''}" onclick='showHostDetails(${JSON.stringify(host)}, "${tenant.url}")'>
                                    <div class="host-name">${host.hostname || 'Unknown'}</div>
                                    <div class="host-status ${isDown ? 'down' : ''}">
                                        ${statusIcon} ${statusText}
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
            
            document.getElementById('total-tenants').textContent = data.length;
            document.getElementById('total-hosts').textContent = totalHosts;
            document.getElementById('issues').textContent = totalIssues;
        }
        
        document.getElementById('sortSelect').addEventListener('change', (e) => {
            const sorted = sortTenants(tenantsData, e.target.value);
            renderTenants(sorted);
        });
        
        fetch('/api/data')
            .then(r => r.json())
            .then(data => {
                tenantsData = data;
                const sorted = sortTenants(data, 'issues-first');
                renderTenants(sorted);
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
                        tenantsData = data;
                        const currentSort = document.getElementById('sortSelect').value;
                        const sorted = sortTenants(data, currentSort);
                        renderTenants(sorted);
                    })
                    .catch(err => console.error('Auto-refresh failed:', err));
            }, AUTO_REFRESH_SECONDS * 1000);
        }
    </script>
</body>
</html>'''

class MMonitHandler(BaseHTTPRequestHandler):
    config = None
    
    def log_message(self, format, *args):
        print(f"{self.address_string()} - {args[0]}")
        
    def do_GET(self):
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            # Replace the auto-refresh placeholder with actual value
            html = HTML_CONTENT.replace('AUTO_REFRESH_INTERVAL_PLACEHOLDER', str(AUTO_REFRESH_INTERVAL))
            self.wfile.write(html.encode('utf-8'))
            
        elif parsed_path.path == '/api/data':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            
            data = query_mmonit_data(self.config['instances'])
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
            
        else:
            self.send_response(404)
            self.end_headers()

def main():
    # Check for config file argument
    config_path = sys.argv[1] if len(sys.argv) > 1 else CONFIG_FILE
    
    # Load configuration
    config = load_config(config_path)
    port = config.get('port', 8080)
    
    # Set config for handler
    MMonitHandler.config = config
    
    # Disable SSL warnings if needed
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    server = HTTPServer(('', port), MMonitHandler)
    print(f'MMonit Hub starting...')
    print(f'Config: {config_path}')
    print(f'Monitoring {len(config["instances"])} tenant(s)')
    print(f'Dashboard: http://localhost:{port}')
    print('Press Ctrl+C to stop\n')
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down...')
        server.shutdown()

if __name__ == '__main__':
    main()