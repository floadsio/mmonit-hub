import requests
import json

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
            session = requests.Session()
            session.get(f"{url}/index.csp", timeout=10, verify=verify_ssl)
            
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
            
            api_version = instance.get('api_version', '2')
            response = session.get(
                f"{url}/api/{api_version}/status/hosts/list",
                params={'results': 1000},
                timeout=10,
                verify=verify_ssl
            )
            
            if response.status_code == 200:
                data = response.json()
                hosts = data.get('records', [])
                
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
                            
                            host_records = detail_data.get('records', {}).get('host', {})
                            platform = host_records.get('platform', {})
                            
                            host['os_name'] = platform.get('name', 'OS N/A')
                            host['os_release'] = platform.get('release', '')
                            
                            filesystems = []
                            issues = []
                            services = host_records.get('services', [])
                            
                            host['service_count'] = len(services) 
                            
                            for service in services:
                                if service.get('type') == 'Filesystem':
                                    stats = service.get('statistics', [])
                                    fs_info = {
                                        'name': service.get('name', 'Unknown'),
                                        'usage_percent': None,
                                        'usage_mb': None,
                                        'total_mb': None
                                    }
                                    for stat in stats:
                                        if stat.get('type') == 18:
                                            fs_info['usage_percent'] = stat.get('value')
                                        elif stat.get('type') == 19:
                                            fs_info['usage_mb'] = stat.get('value')
                                        elif stat.get('type') == 20:
                                            fs_info['total_mb'] = stat.get('value')
                                    if fs_info['usage_percent'] is not None:
                                        filesystems.append(fs_info)

                                if service.get('led') in [0, 1]:
                                    issues.append({
                                        'name': service.get('name', 'Unknown'),
                                        'type': service.get('type', 'Unknown'),
                                        'status': service.get('status', 'Unknown'),
                                        'led': service.get('led')
                                    })
                            
                            host['filesystems'] = filesystems
                            host['issues'] = issues
                        else:
                            host['filesystems'] = []; host['issues'] = []; host['service_count'] = 0; host['os_name'] = 'OS N/A'; host['os_release'] = ''
                    except Exception as e:
                        host['filesystems'] = []; host['issues'] = []; host['service_count'] = 0; host['os_name'] = 'OS N/A'; host['os_release'] = ''

                
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