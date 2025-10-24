# data_fetcher.py
import hashlib
from threading import RLock
from typing import Dict, Any, List

import requests

DEFAULT_TIMEOUT = 12  # seconds

# In-memory cache keyed per Healthchecks project so we can prune stale checks.
_HEALTHCHECK_CACHE: Dict[str, Dict[str, Dict[str, Any]]] = {}
_HEALTHCHECK_CACHE_LOCK = RLock()


def _hc_status_to_led(status: str) -> int:
    """Map Healthchecks status to M/Monit LED codes: 2=OK, 1=Warn, 0=Error."""
    s = (status or "").lower()
    if s == "up":
        return 2
    if s in ("grace", "paused", "new"):
        return 1
    if s == "down":
        return 0
    return 1


def _project_cache_key(instance: Dict[str, Any], project: Dict[str, Any], api_base: str) -> str:
    """Generate a stable cache key without exposing sensitive API keys."""
    tenant_name = (instance.get("name") or "tenant").strip() or "tenant"
    project_label = (project.get("name") or "").strip() or "project"
    tags_part = " ".join(sorted(project.get("tags") or []))
    include_paused = "1" if project.get("include_paused", False) else "0"
    api_key = project.get("api_key") or ""
    digest_material = "|".join([api_base, project_label, tags_part, include_paused])
    digest = hashlib.sha256(f"{api_key}|{digest_material}".encode("utf-8")).hexdigest()[:16]
    return f"{tenant_name}:{digest}"


def _update_healthchecks_cache(cache_key: str, hosts: List[Dict[str, Any]], context: str) -> None:
    """Record the current set of checks and drop any that disappeared upstream."""
    host_index: Dict[str, Dict[str, Any]] = {}
    for host in hosts:
        host_id = host.get("id")
        if host_id is None or host_id == "":
            fallback = (host.get("hostname") or "").strip() or "unnamed"
            host_id = f"name:{fallback}"
        else:
            host_id = str(host_id)
        host_index[host_id] = host

    with _HEALTHCHECK_CACHE_LOCK:
        previous = _HEALTHCHECK_CACHE.get(cache_key) or {}
        removed_ids = set(previous.keys()) - set(host_index.keys())
        if removed_ids:
            removed_names = [previous[rid].get("hostname", rid) for rid in removed_ids]
            preview = ", ".join(removed_names[:3])
            if len(removed_names) > 3:
                preview += f", +{len(removed_names) - 3} more"
            print(f"[HC] pruned {len(removed_ids)} stale check(s) for {context}: {preview}", flush=True)
        _HEALTHCHECK_CACHE[cache_key] = host_index


def fetch_healthchecks_for_tenant(instance: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Fetch Healthchecks.io checks for a specific tenant.

    Expected config on each instance:
      "healthchecks": {
        "enabled": true,
        "projects": [
          {
            "name": "Prod Project",
            "api_base": "https://healthchecks.io",  # optional
            "api_key": "<read_key>",
            "tags": ["prod", "web"],                # optional filters; empty => all checks
            "include_paused": false,                # optional
            "verify_ssl": true                      # optional, default True
          }
        ]
      }
    """
    hc_cfg = (instance or {}).get("healthchecks", {})
    if not hc_cfg or not hc_cfg.get("enabled") or not hc_cfg.get("projects"):
        return []

    merged: List[Dict[str, Any]] = []

    for proj in hc_cfg["projects"]:
        api_base = (proj.get("api_base") or "https://healthchecks.io").rstrip("/")
        api_key = proj.get("api_key")
        tags = proj.get("tags") or []
        include_paused = bool(proj.get("include_paused", False))
        verify_ssl = proj.get("verify_ssl", True)

        if not api_key:
            # Skip silently if no key so other projects can load
            continue

        url = f"{api_base}/api/v3/checks/"
        params = [("tag", t) for t in tags]  # multiple tag params => AND filter on HC
        cache_key = _project_cache_key(instance, proj, api_base)
        tenant_label = instance.get("name") or "tenant"
        project_label = proj.get("name") or f"Healthchecks @ {api_base}"
        context_label = f"{tenant_label}/{project_label}"

        try:
            r = requests.get(
                url,
                headers={"X-Api-Key": api_key},
                params=params,
                timeout=DEFAULT_TIMEOUT,
                verify=verify_ssl,
            )
            r.raise_for_status()
            payload = r.json() or {}
        except Exception as e:
            merged.append({
                "hostname": f"[Healthchecks] {proj.get('name', 'Project')}",
                "led": 0,
                "cpu": 0, "mem": 0, "events": 0, "heartbeat": False,
                "id": f"hcproj:{proj.get('name', 'project')}",
                "os_name": "Healthchecks",
                "os_release": (proj.get("name") or ""),
                "filesystems": [],
                "issues": [{"name": "Healthchecks API error", "type": "HTTP", "status": str(e), "led": 0}],
                "service_count": 0,
                "service_names": ["healthchecks-api-error"],
                "services_detail": [],
                "source": "healthchecks",
                "css_class": "healthchecks",
                "view_url": f"{api_base}/projects",
            })
            continue

        project_hosts: List[Dict[str, Any]] = []

        for c in payload.get("checks", []):
            status = (c.get("status") or "new").lower()
            if status == "paused" and not include_paused:
                continue

            led = _hc_status_to_led(status)
            name = c.get("name") or c.get("slug") or "Unnamed Check"
            tags_str = c.get("tags") or ""
            tag_list = [t for t in tags_str.split() if t]

            unique_key = c.get("unique_key")
            check_view = f"{api_base}/checks/{unique_key}" if unique_key else api_base

            project_hosts.append({
                "hostname": name,
                "led": led,
                "cpu": 0,
                "mem": 0,
                "events": 0,
                "heartbeat": status in ("up", "grace"),
                "id": f"hc:{c.get('id') or unique_key or name}",
                "os_name": "Healthchecks",
                "os_release": " ".join(tag_list),
                "filesystems": [],
                "issues": [] if status == "up" else [{
                    "name": "Healthcheck",
                    "type": "Ping",
                    "status": status.upper(),
                    "led": led
                }],
                "service_count": len(tag_list),
                "service_names": tag_list,
                "services_detail": [
                    {
                        "name": t,
                        "type": "Tag",
                        "status": "OK" if status == "up" else status.upper(),
                        "led": led
                    } for t in tag_list
                ],
                "source": "healthchecks",
                "css_class": "healthchecks",
                "view_url": check_view,
            })

        _update_healthchecks_cache(cache_key, project_hosts, context_label)
        merged.extend(project_hosts)

    return merged


def query_mmonit_data(instances: List[Dict[str, Any]], allowed_tenants=None) -> List[Dict[str, Any]]:
    """Aggregate data from all M/Monit instances and integrate Healthchecks.io."""
    result: List[Dict[str, Any]] = []

    for instance in instances:
        name = instance["name"]

        # Tenant filtering
        if allowed_tenants and "*" not in allowed_tenants and name not in allowed_tenants:
            continue

        url = instance["url"]
        username = instance["username"]
        password = instance["password"]
        verify_ssl = instance.get("verify_ssl", False)

        hosts: List[Dict[str, Any]] = []
        error = None

        try:
            session = requests.Session()
            session.get(f"{url}/index.csp", timeout=DEFAULT_TIMEOUT, verify=verify_ssl)

            login_response = session.post(
                f"{url}/z_security_check",
                data={"z_username": username, "z_password": password, "z_csrf_protection": "off"},
                timeout=DEFAULT_TIMEOUT,
                verify=verify_ssl,
            )

            if login_response.status_code != 200:
                error = f"Login failed: HTTP {login_response.status_code}"
            else:
                api_version = instance.get("api_version", "2")
                response = session.get(
                    f"{url}/api/{api_version}/status/hosts/list",
                    params={"results": 1000},
                    timeout=DEFAULT_TIMEOUT,
                    verify=verify_ssl,
                )

                if response.status_code == 200:
                    data = response.json() or {}
                    hosts = data.get("records", []) or []

                    for host in hosts:
                        try:
                            detail_response = session.get(
                                f"{url}/api/{api_version}/status/hosts/get",
                                params={"id": host["id"]},
                                timeout=DEFAULT_TIMEOUT,
                                verify=verify_ssl,
                            )
                            if detail_response.status_code == 200:
                                detail_data = detail_response.json() or {}
                                host_records = (detail_data.get("records") or {}).get("host", {}) or {}
                                platform = host_records.get("platform", {}) or {}

                                host["os_name"] = platform.get("name", "OS N/A")
                                host["os_release"] = platform.get("release", "")

                                filesystems: List[Dict[str, Any]] = []
                                issues: List[Dict[str, Any]] = []
                                services = host_records.get("services", []) or []
                                host["service_count"] = len(services)
                                host["source"] = "mmonit"
                                host["css_class"] = ""
                                host["view_url"] = f"{url}/admin/hosts/get?id={host['id']}"

                                # Build services_detail + service_names for the UI
                                services_detail: List[Dict[str, Any]] = []
                                service_names: List[str] = []

                                for service in services:
                                    # Disk usage extraction
                                    if service.get("type") == "Filesystem":
                                        stats = service.get("statistics", []) or []
                                        fs_info = {
                                            "name": service.get("name", "Unknown"),
                                            "usage_percent": None,
                                            "usage_mb": None,
                                            "total_mb": None,
                                        }
                                        for stat in stats:
                                            t = stat.get("type")
                                            if t == 18:
                                                fs_info["usage_percent"] = stat.get("value")
                                            elif t == 19:
                                                fs_info["usage_mb"] = stat.get("value")
                                            elif t == 20:
                                                fs_info["total_mb"] = stat.get("value")
                                        if fs_info["usage_percent"] is not None:
                                            filesystems.append(fs_info)

                                    # Build issues from non-green services
                                    if service.get("led") in (0, 1):
                                        issues.append({
                                            "name": service.get("name", "Unknown"),
                                            "type": service.get("type", "Unknown"),
                                            "status": service.get("status", "Unknown"),
                                            "led": service.get("led"),
                                        })

                                    services_detail.append({
                                        "name": service.get("name", "Unknown"),
                                        "type": service.get("type", "Unknown"),
                                        "status": service.get("status", "Unknown"),
                                        "led": service.get("led", 2),
                                    })
                                    if service.get("name"):
                                        service_names.append(service["name"])

                                host["filesystems"] = filesystems
                                host["issues"] = issues
                                host["services_detail"] = services_detail
                                host["service_names"] = service_names

                            else:
                                host.update({
                                    "filesystems": [],
                                    "issues": [],
                                    "service_count": 0,
                                    "os_name": "OS N/A",
                                    "os_release": "",
                                    "source": "mmonit",
                                    "css_class": "",
                                    "services_detail": [],
                                    "service_names": [],
                                    "view_url": f"{url}/admin/hosts/get?id={host['id']}",
                                })
                        except Exception:
                            host.update({
                                "filesystems": [],
                                "issues": [],
                                "service_count": 0,
                                "os_name": "OS N/A",
                                "os_release": "",
                                "source": "mmonit",
                                "css_class": "",
                                "services_detail": [],
                                "service_names": [],
                                "view_url": f"{url}/admin/hosts/get?id={host.get('id', 0)}",
                            })

                else:
                    error = f"API error: HTTP {response.status_code}"

        except requests.exceptions.Timeout:
            error = "Connection timeout"
        except requests.exceptions.ConnectionError:
            error = "Connection failed"
        except Exception as e:
            error = str(e)

        # Merge Healthchecks.io results (never interrupts M/Monit data)
        try:
            hc_hosts = fetch_healthchecks_for_tenant(instance)
            print(f"[HC] tenant={name} projects="
                f"{len((instance.get('healthchecks', {}) or {}).get('projects', []))} "
                f"hosts_returned={len(hc_hosts)}", flush=True)
        except Exception as e:
            hc_hosts = [{
                "hostname": "[Healthchecks] Merge Error",
                "led": 1,
                "cpu": 0, "mem": 0, "events": 0, "heartbeat": False,
                "id": "hc:merge-error",
                "os_name": "Healthchecks",
                "os_release": "",
                "filesystems": [],
                "issues": [{"name": "Healthchecks merge", "type": "Runtime", "status": str(e), "led": 1}],
                "service_count": 0,
                "service_names": [],
                "services_detail": [],
                "source": "healthchecks",
                "css_class": "healthchecks",
                "view_url": None,
            }]

        merged_hosts = (hosts or []) + hc_hosts

        entry = {"tenant": name, "url": url, "hosts": merged_hosts}
        if error:
            entry["error"] = error

        result.append(entry)

    return result
