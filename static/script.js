/* static/script.js — full file with robust auto/light/dark theme mode */

let tenantsData = [];
let showOnlyIssues = false;
let activeHostTypeFilter = null;

const SHOW_ONLY_ISSUES_KEY = 'show_only_issues';
const HOST_TYPE_FILTER_KEY = 'host_type_filter';

try {
  const storedHostFilter = localStorage.getItem(HOST_TYPE_FILTER_KEY);
  if (storedHostFilter && storedHostFilter.trim() !== '') {
    const normalized = storedHostFilter.trim().toLowerCase();
    activeHostTypeFilter = normalized === 'os n/a' ? null : normalized;
  }
} catch (e) {
  activeHostTypeFilter = null;
}

/* ----------------------- Config from server / defaults ----------------------- */
const DISK_WARN = Number(window.DISK_WARN_PCT ?? 80);
const DISK_ERR  = Number(window.DISK_ERR_PCT  ?? 90);

/* ---------------------------------- THEME ---------------------------------- */
/* 3-state theme mode:
   - 'auto'  : follow OS, live updates on system change
   - 'light' : force light
   - 'dark'  : force dark
*/
const THEME_MODE_KEY = 'theme_mode';

function getSystemPrefersDark() {
  try { return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches; }
  catch { return false; }
}

function iconForMode(mode) {
  return mode === 'auto' ? '🌓' : mode === 'light' ? '☀️' : '🌙';
}

function applyThemeFromMode(mode, persist=true) {
  let theme = 'light';
  if (mode === 'auto') {
    theme = getSystemPrefersDark() ? 'dark' : 'light';
  } else {
    theme = mode; // 'light' or 'dark'
  }
  document.documentElement.setAttribute('data-theme', theme);
  document.documentElement.style.colorScheme = theme;

  const iconEl = document.getElementById('themeIcon');
  if (iconEl) iconEl.textContent = iconForMode(mode);

  if (persist) {
    try { localStorage.setItem(THEME_MODE_KEY, mode); } catch(e) {}
  }
}

function initTheme() {
  // pick mode
  let mode = 'auto';
  try {
    const saved = localStorage.getItem(THEME_MODE_KEY);
    if (saved === 'auto' || saved === 'light' || saved === 'dark') mode = saved;
  } catch(e) {}

  applyThemeFromMode(mode, false);

  // live OS updates when in 'auto'
  const mq = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
  if (mq) {
    const handler = () => {
      const current = (localStorage.getItem(THEME_MODE_KEY) || 'auto');
      if (current === 'auto') applyThemeFromMode('auto', false);
    };
    try { mq.addEventListener('change', handler); }
    catch { mq.addListener(handler); } // Safari fallback
  }

  // toggle cycles through modes
  const toggle = document.getElementById('themeToggle');
  if (toggle) {
    toggle.addEventListener('click', () => {
      const current = (localStorage.getItem(THEME_MODE_KEY) || 'auto');
      const next = current === 'auto' ? 'light' : current === 'light' ? 'dark' : 'auto';
      applyThemeFromMode(next, true);
    });
  }
}

/* ------------------------------ UTIL FUNCTIONS ------------------------------ */

function getDiskAlert(host) {
  if (!host.filesystems || host.filesystems.length === 0) return { alert: null, max: 0 };
  const max = host.filesystems.reduce((m, fs) => Math.max(m, fs.usage_percent || 0), 0);
  if (max >= DISK_ERR)  return { alert: 'error',   max };
  if (max >= DISK_WARN) return { alert: 'warning', max };
  return { alert: null, max };
}

function hostHasIssue(host) {
  if (!host) return false;
  if (host.led !== 2) return true;
  const disk = getDiskAlert(host);
  return !!disk.alert;
}

function normalizeHostType(name) {
  if (!name) return '';
  const normalized = String(name).trim().toLowerCase();
  return normalized === 'os n/a' ? '' : normalized;
}

function persistHostTypeFilter() {
  try {
    if (activeHostTypeFilter) {
      localStorage.setItem(HOST_TYPE_FILTER_KEY, activeHostTypeFilter);
    } else {
      localStorage.removeItem(HOST_TYPE_FILTER_KEY);
    }
  } catch (e) {
    // ignore persistence failures (e.g., private browsing)
  }
}

function clearHostTypeFilter() {
  activeHostTypeFilter = null;
  persistHostTypeFilter();
}

function toggleHostTypeFilter(norm) {
  const normalized = normalizeHostType(norm);
  const nextFilter = normalized && activeHostTypeFilter !== normalized ? normalized : null;
  activeHostTypeFilter = nextFilter;
  persistHostTypeFilter();

  const sortEl = document.getElementById('sortSelect');
  const sortValue = sortEl ? sortEl.value : 'issues-first';
  const sorted = sortTenants(tenantsData, sortValue);
  renderTenantsOnly(sorted);
}

// Prefer Healthchecks (or backend-provided) deep-link when available
function getHostExternalLink(host, tenantUrl) {
  if (host.view_url) return host.view_url; // Healthchecks or explicit link from backend
  if (tenantUrl && host.id != null) return `${tenantUrl}/admin/hosts/get?id=${host.id}`; // M/Monit fallback
  return '#';
}

// Extra CSS class for host cards (e.g., Healthchecks)
function hostExtraClass(host) {
  if (host && typeof host.css_class === 'string' && host.css_class.trim() !== '') {
    return host.css_class.trim();
  }
  if (host && host.source === 'healthchecks') return 'healthchecks';
  return '';
}

// Version comparison helper
function compareVersions(v1, v2) {
  v1 = v1 || '0'; v2 = v2 || '0';
  const a = v1.split('-')[0].split('.');
  const b = v2.split('-')[0].split('.');
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const n1 = parseInt(a[i]) || 0, n2 = parseInt(b[i]) || 0;
    if (n1 < n2) return -1;
    if (n1 > n2) return 1;
  }
  return 0;
}

function displayTimeInfo(lastFetchUnix, refreshSeconds) {
  const lastUpdateElement = document.getElementById('last-update');
  const intervalElement = document.getElementById('refresh-interval-display');
  if (lastFetchUnix) {
    const date = new Date(lastFetchUnix * 1000);
    lastUpdateElement.textContent = 'Last Updated: ' + date.toLocaleTimeString();
  } else {
    lastUpdateElement.textContent = 'Last Updated: N/A';
  }
  intervalElement.textContent = refreshSeconds > 0
    ? 'Auto-refresh: ' + refreshSeconds + 's'
    : 'Auto-refresh: Disabled';
}

function updateIssuesCardState() {
  const card = document.getElementById('issues-card');
  if (!card) return;
  card.classList.toggle('issues-toggle-active', showOnlyIssues);
  card.setAttribute('aria-pressed', showOnlyIssues ? 'true' : 'false');
  const title = showOnlyIssues
    ? 'Showing only hosts with issues. Click to show all hosts.'
    : 'Click to show only hosts with issues.';
  card.setAttribute('title', title);
}

function initIssuesToggle() {
  const card = document.getElementById('issues-card');
  if (!card) return;

  try {
    showOnlyIssues = localStorage.getItem(SHOW_ONLY_ISSUES_KEY) === '1';
  } catch (e) {
    showOnlyIssues = false;
  }

  card.setAttribute('role', 'button');
  card.setAttribute('tabindex', '0');
  updateIssuesCardState();

  const triggerRender = () => {
    const sortValue = (document.getElementById('sortSelect') || { value: 'issues-first' }).value;
    const sorted = sortTenants(tenantsData, sortValue);
    renderTenantsOnly(sorted);
  };

  card.addEventListener('click', () => {
    showOnlyIssues = !showOnlyIssues;
    try {
      localStorage.setItem(SHOW_ONLY_ISSUES_KEY, showOnlyIssues ? '1' : '0');
    } catch (e) {
      // ignore persistence errors
    }
    updateIssuesCardState();
    triggerRender();
  });

  card.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      card.click();
    }
  });

  if (showOnlyIssues && tenantsData.length > 0) {
    triggerRender();
  }
}

/* -------------------------------- OS STATS -------------------------------- */

function renderOSStats(allHosts) {
  const counts = {};
  const labels = {};

  allHosts.forEach(host => {
    const rawName = host && host.os_name ? String(host.os_name).trim() : '';
    if (!rawName || rawName.toUpperCase() === 'OS N/A') return;
    const norm = normalizeHostType(rawName);
    if (!norm) return;
    counts[norm] = (counts[norm] || 0) + 1;
    if (!labels[norm]) labels[norm] = rawName;
  });

  const container = document.getElementById('os-stats-container');
  container.innerHTML = '';

  const entries = Object.keys(counts).map(norm => ({
    norm,
    count: counts[norm],
    label: labels[norm]
  })).sort((a, b) => b.count - a.count);

  if (entries.length === 0) {
    container.style.display = 'none';
    return;
  }

  container.style.display = 'grid';

  const activeNorm = activeHostTypeFilter;
  let cards = entries.slice(0, 4);
  if (activeNorm && counts[activeNorm] && !cards.some(entry => entry.norm === activeNorm)) {
    const activeEntry = entries.find(entry => entry.norm === activeNorm);
    if (activeEntry) {
      if (cards.length >= 4) cards.pop();
      cards.push(activeEntry);
    }
  }
  cards = cards.sort((a, b) => b.count - a.count);

  cards.forEach(entry => {
    const card = document.createElement('div');
    card.className = 'stat-card os-stat-card';
    const isActive = entry.norm === activeNorm;
    if (isActive) card.classList.add('os-card-active');
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    card.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    const displayLabel = entry.label || 'Unknown';
    const labelText = displayLabel.toUpperCase() + ' HOSTS';
    card.setAttribute('title', isActive
      ? 'Showing only ' + displayLabel + ' hosts. Click to show all hosts.'
      : 'Click to show only ' + displayLabel + ' hosts.');
    card.innerHTML =
      '<div class="stat-value">' + entry.count + '</div>' +
      '<div class="stat-label">' + labelText + '</div>';

    const activate = () => toggleHostTypeFilter(entry.norm);
    card.addEventListener('click', activate);
    card.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        activate();
      }
    });

    container.appendChild(card);
  });
}

/* --------------------------------- MODAL ---------------------------------- */

function showHostDetails(host, tenantUrl) {
  const modal = document.getElementById('hostModal');
  const modalTitle = document.getElementById('modalTitle');
  const modalBody = document.getElementById('modalBody');

  const statusClass = host.led === 0 ? 'error' : (host.led === 1 ? 'warning' : 'ok');
  const statusText  = host.led === 0 ? 'Error' : (host.led === 1 ? 'Warning' : 'OK');

  let filesystemsHtml = '';
  if (host.filesystems && host.filesystems.length > 0) {
    filesystemsHtml = '<div class="detail-row"><div class="detail-label">Filesystems</div><div class="detail-value">';
    host.filesystems.forEach(fs => {
      const usageClass = fs.usage_percent >= DISK_ERR ? 'error'
                       : (fs.usage_percent >= DISK_WARN ? 'warning' : 'ok');
      filesystemsHtml += '<div style="margin-bottom:8px;"><div><strong>' + fs.name + '</strong></div>' +
        '<div><span class="status-indicator ' + usageClass + '">' + fs.usage_percent.toFixed(1) + '%</span>' +
        (fs.usage_mb !== null ? ' ' + (fs.usage_mb/1024).toFixed(1) + ' GB / ' + (fs.total_mb/1024).toFixed(1) + ' GB' : '') +
        '</div></div>';
    });
    filesystemsHtml += '</div></div>';
  }

  let issuesDetailsHtml = '';
  if (host.issues && host.issues.length > 0) {
    issuesDetailsHtml = '<div class="detail-row"><div class="detail-label">Service Issues</div><div class="detail-value">';
    host.issues.forEach(issue => {
      const cls = issue.led === 0 ? 'error' : 'warning';
      issuesDetailsHtml += '<div style="margin-bottom:8px;"><div><strong>' + issue.name + '</strong> (' + issue.type + ')</div>' +
        '<div><span class="status-indicator ' + cls + '">' + issue.status + '</span></div></div>';
    });
    issuesDetailsHtml += '</div></div>';
  }

  // Services list
  let servicesDetailsHtml = '';
  if (host.services_detail && host.services_detail.length > 0) {
    servicesDetailsHtml = '<div class="detail-row services-row"><div class="detail-label">Services</div><div class="detail-value" style="width:100%;">';
    host.services_detail.forEach(svc => {
      const svcClass = svc.led === 0 ? 'error' : (svc.led === 1 ? 'warning' : 'ok');
      servicesDetailsHtml += '<div class="service-item">' +
        '<div><strong>' + svc.name + '</strong> <span style="color:var(--text-secondary)">(' + svc.type + ')</span></div>' +
        '<div><span class="status-indicator ' + svcClass + '">' + (svc.status || (svc.led === 2 ? 'OK' : '')) + '</span></div>' +
        '</div>';
    });
    servicesDetailsHtml += '</div></div>';
  }

  const externalHref = getHostExternalLink(host, tenantUrl);
  const externalLabel = host.source === 'healthchecks' ? 'Healthchecks' : 'M/Monit';

  modalTitle.textContent = host.hostname;
  modalBody.innerHTML =
    '<div class="detail-row">' +
      '<div class="detail-label">Status</div>' +
      '<div class="detail-value"><span class="status-indicator ' + statusClass + '">' + statusText + '</span></div>' +
    '</div>' +
    issuesDetailsHtml +
    servicesDetailsHtml +
    '<div class="detail-row"><div class="detail-label">Operating System</div>' +
      '<div class="detail-value">' + host.os_name + ' (' + (host.os_release || 'N/A') + ')</div></div>' +
    '<div class="detail-row"><div class="detail-label">CPU Usage</div><div class="detail-value">' + host.cpu + '%</div></div>' +
    '<div class="detail-row"><div class="detail-label">Memory Usage</div><div class="detail-value">' + host.mem + '%</div></div>' +
    '<div class="detail-row"><div class="detail-label">Events</div><div class="detail-value">' + host.events + '</div></div>' +
    '<div class="detail-row"><div class="detail-label">Heartbeat</div><div class="detail-value">' + (host.heartbeat ? '✓ Active' : '✗ Inactive') + '</div></div>' +
    '<div class="detail-row"><div class="detail-label">Host ID</div><div class="detail-value">' + host.id + '</div></div>' +
    filesystemsHtml +
    '<div style="margin-top:20px; text-align:center;">' +
      '<a href="' + externalHref + '" target="_blank" class="refresh">View in ' + externalLabel + ' →</a>' +
    '</div>';

  modal.classList.add('show');
}

function closeModal(){
  const m = document.getElementById('hostModal');
  if (m) m.classList.remove('show');
}

/* ------------------------------ RENDERING ------------------------------ */

function sortTenants(data, sortBy){
  const sorted = [...data];
  switch(sortBy){
    case 'issues-first':
      return sorted.sort((a,b)=>{
        const ai = a.error ? 10000 : (a.hosts||[]).filter(h=>h.led!==2).length;
        const bi = b.error ? 10000 : (b.hosts||[]).filter(h=>h.led!==2).length;
        if (ai!==bi) return bi-ai;
        const ah=(a.hosts||[]).length, bh=(b.hosts||[]).length;
        return bh-ah;
      });
    case 'name':
      return sorted.sort((a,b)=> a.tenant.localeCompare(b.tenant));
    case 'hosts':
      return sorted.sort((a,b)=> (b.hosts||[]).length - (a.hosts||[]).length);
    case 'cpu':
      return sorted.sort((a,b)=>{
        const av=(a.hosts||[]).reduce((s,h)=>s+(h.cpu||0),0)/((a.hosts||[]).length||1);
        const bv=(b.hosts||[]).reduce((s,h)=>s+(h.cpu||0),0)/((b.hosts||[]).length||1);
        return bv-av;
      });
    case 'memory':
      return sorted.sort((a,b)=>{
        const av=(a.hosts||[]).reduce((s,h)=>s+(h.mem||0),0)/((a.hosts||[]).length||1);
        const bv=(b.hosts||[]).reduce((s,h)=>s+(h.mem||0),0)/((b.hosts||[]).length||1);
        return bv-av;
      });
    case 'disk':
      return sorted.sort((a,b)=>{
        const avg = (t)=>{
          const arr=(t.hosts||[]).map(h=>Math.max(...(h.filesystems||[]).map(fs=>fs.usage_percent||0),0));
          return arr.length? arr.reduce((s,x)=>s+x,0)/arr.length : 0;
        };
        return avg(b)-avg(a);
      });
    case 'os':
      return sorted.sort((a,b)=>{
        const ao=(a.hosts[0]&&a.hosts[0].os_name)||'zzzzzz';
        const bo=(b.hosts[0]&&b.hosts[0].os_name)||'zzzzzz';
        return ao.localeCompare(bo);
      });
    case 'os-version':
      return sorted.sort((a,b)=>{
        const av=(a.hosts||[]).map(h=>h.os_release||'0').sort(compareVersions)[0];
        const bv=(b.hosts||[]).map(h=>h.os_release||'0').sort(compareVersions)[0];
        return compareVersions(av,bv);
      });
    case 'os-update-needed':
      return sorted.sort((a,b)=>{
        const an=(a.hosts||[]).some(h=>!h.os_release);
        const bn=(b.hosts||[]).some(h=>!h.os_release);
        if (an && !bn) return -1;
        if (!an && bn) return 1;
        const ai=a.error?1000:(a.hosts||[]).filter(h=>h.led!==2).length;
        const bi=b.error?1000:(b.hosts||[]).filter(h=>h.led!==2).length;
        return bi-ai;
      });
    default:
      return sorted;
  }
}

function renderOSStatsAndCards(processedTenants){
  const allHosts = processedTenants.flatMap(t=>t.hosts||[]);
  renderOSStats(allHosts);

  let totalHosts=0,totalIssues=0,totalServices=0;
  processedTenants.forEach(t=>{
    const hosts=t.hosts||[];
    totalHosts+=hosts.length;
    totalIssues+=hosts.filter(hostHasIssue).length;
    totalServices+=hosts.reduce((s,h)=>s+(h.service_count||0),0);
  });

  const issuesCard = document.getElementById('issues-card');
  issuesCard.className='stat-card';
  if (totalIssues>0){
    const hasError = processedTenants.flatMap(t=>t.hosts||[]).some(h=>{
      const d=getDiskAlert(h);
      return (h.issues||[]).some(i=>i.led===0) || d.alert==='error';
    });
    issuesCard.classList.add(hasError?'issue-card-error':'issue-card-warn');
  } else {
    issuesCard.classList.add('issue-card-ok');
  }

  document.getElementById('total-tenants').textContent = processedTenants.length;
  document.getElementById('total-hosts').textContent   = totalHosts;
  document.getElementById('total-services').textContent= totalServices;
  document.getElementById('issues').textContent        = totalIssues;
}

function renderTenants(data){
  const processedTenants = data.tenants;
  const container = document.getElementById('tenants');
  container.innerHTML='';

  renderOSStatsAndCards(processedTenants);

  processedTenants.forEach(tenant=>{
    const div=document.createElement('div'); div.className='tenant';
    if (tenant.error){
      div.classList.add('error');
      div.innerHTML =
        '<div class="tenant-header">' +
          '<div><div class="tenant-name">' + tenant.tenant + '</div><div class="tenant-url">' + tenant.url + '</div></div>' +
          '<span class="status-badge badge-error">ERROR</span></div>' +
          '<div class="error-msg">⚠️ ' + tenant.error + '</div>';
    } else {
      const hosts = tenant.hosts||[];
      const issues = hosts.filter(hostHasIssue).length;
      div.classList.add(issues>0?'issues':'ok');

      let hostsHtml = '<div class="hosts">';
      hosts.forEach(host=>{
        const isDown = host.led!==2;
        const disk = getDiskAlert(host);
        const cardSeverityClass = isDown ? 'error' : (disk.alert ? 'warn' : '');
        const extraCls = hostExtraClass(host);
        const icon = host.led===0?'🔴':(host.led===1?'🟡':'🟢');
        const text = host.led===0?'Error':(host.led===1?'Warning':'Running');
        const diskInfo = disk.max>0 ? ' | Disk: ' + disk.max.toFixed(1) + '%' : '';
        const sourceBadge = host.source === 'healthchecks' ? '<span class="source-badge" title="Healthchecks">HC</span>' : '';

        let issuesHtml='';
        if (host.issues && host.issues.length>0){
          const errs=host.issues.filter(i=>i.led===0), warns=host.issues.filter(i=>i.led===1);
          if (errs.length>0) issuesHtml = '<div class="host-issues">⚠️ ' + errs.map(i=>i.name).join(', ') + '</div>';
          else if (warns.length>0) issuesHtml = '<div class="host-issues warning">⚠️ ' + warns.map(i=>i.name).join(', ') + '</div>';
        } else if (disk.alert){
          const cls = disk.alert==='error' ? '' : ' warning';
          issuesHtml = '<div class="host-issues' + cls + '">⚠️ Disk usage ' + disk.max.toFixed(1) + '%</div>';
        }

        const os_name = host.os_name || 'OS N/A';
        const os_release = host.os_release || '';
        const hostName = host.hostname || 'Unknown';
        const filterText = document.getElementById('hostFilter').value.toLowerCase();
        const serviceText = (host.service_names||[]).join(' ');
        const searchable = (hostName + ' ' + os_name + ' ' + os_release + ' ' + serviceText).toLowerCase();
        const hidden = filterText && !searchable.includes(filterText) ? 'hidden' : '';

        hostsHtml += '<div class="host ' + cardSeverityClass + ' ' + extraCls + ' ' + hidden +
          '" onclick=\'showHostDetails(' + JSON.stringify(host) + ', "' + tenant.url + '")\'>' +
          '<div class="host-name">' + hostName + ' ' + sourceBadge + '</div>' +
          '<div class="host-status ' + (isDown?'down':'') + '"><span>' + icon + ' ' + text + '</span><span class="os-info">' + os_name + (os_release?(' '+os_release):'') + '</span></div>' +
          '<div class="host-details">CPU: ' + host.cpu + '% | Mem: ' + host.mem + '%' + diskInfo + '</div>' +
          issuesHtml +
          '</div>';
      });
      hostsHtml+='</div>';

      div.innerHTML =
        '<div class="tenant-header">' +
          '<div><div class="tenant-name" onclick="window.open(\'' + tenant.url + '\', \'_blank\')">' + tenant.tenant + '</div>' +
          '<div class="tenant-url">' + tenant.url + '</div></div>' +
          '<span class="status-badge ' + (issues>0?'badge-warning':'badge-ok') + '">' + hosts.length + ' hosts • ' + issues + ' issues</span>' +
        '</div>' + hostsHtml;
    }
    container.appendChild(div);
  });

  displayTimeInfo(data.last_fetch_time, data.refresh_interval);
  tenantsData = processedTenants;
  const currentSort = document.getElementById('sortSelect').value;
  const sorted = sortTenants(processedTenants, currentSort);
  renderTenantsOnly(sorted);
}

function renderTenantsOnly(data){
  const container=document.getElementById('tenants'); container.innerHTML='';
  let totalHosts=0,totalIssues=0,totalServices=0;
  const allDisplayedHosts = [];
  const filterText = document.getElementById('hostFilter').value.toLowerCase();
  const selectedSort = document.getElementById('sortSelect').value;
  const allHosts = data.flatMap(t=>t.hosts||[]);

  let effectiveActiveFilter = activeHostTypeFilter;
  if (effectiveActiveFilter) {
    const hasMatchingHosts = allHosts.some(host => normalizeHostType(host && host.os_name) === effectiveActiveFilter);
    if (!hasMatchingHosts) {
      clearHostTypeFilter();
      effectiveActiveFilter = null;
    }
  }

  data.forEach(tenant=>{
    const hosts=tenant.hosts||[];
    const issues = hosts.filter(hostHasIssue).length;
    totalHosts+=hosts.length;
    totalIssues+=issues;
    totalServices+=hosts.reduce((s,h)=>s+(h.service_count||0),0);

    if (tenant.error){
      const div=document.createElement('div'); div.className='tenant';
      div.classList.add('error');
      div.innerHTML =
        '<div class="tenant-header"><div><div class="tenant-name">' + tenant.tenant + '</div>' +
        '<div class="tenant-url">' + tenant.url + '</div></div><span class="status-badge badge-error">ERROR</span></div>' +
        '<div class="error-msg">⚠️ ' + tenant.error + '</div>';
      container.appendChild(div);
      return;
    }

    let renderedHosts = hosts;
    if (showOnlyIssues) {
      renderedHosts = renderedHosts.filter(hostHasIssue);
    }
    if (effectiveActiveFilter) {
      renderedHosts = renderedHosts.filter(host=>normalizeHostType(host && host.os_name) === effectiveActiveFilter);
    }
    if (renderedHosts.length === 0) return;

    const div=document.createElement('div'); div.className='tenant';
    {
      div.classList.add(issues>0?'issues':'ok');

      let hostsHtml='<div class="hosts">';
      renderedHosts.forEach(host=>{
        const isDown=host.led!==2;
        const disk = getDiskAlert(host);
        const cardSeverityClass = isDown ? 'error' : (disk.alert ? 'warn' : '');
        const extraCls = hostExtraClass(host);
        const icon=host.led===0?'🔴':(host.led===1?'🟡':'🟢');
        const text=host.led===0?'Error':(host.led===1?'Warning':'Running');
        const diskInfo = disk.max>0 ? ' | Disk: ' + disk.max.toFixed(1) + '%' : '';
        const sourceBadge = host.source === 'healthchecks' ? '<span class="source-badge" title="Healthchecks">HC</span>' : '';

        let issuesHtml='';
        if (host.issues && host.issues.length>0){
          const errs=host.issues.filter(i=>i.led===0), warns=host.issues.filter(i=>i.led===1);
          if (errs.length>0) issuesHtml = '<div class="host-issues">⚠️ ' + errs.map(i=>i.name).join(', ') + '</div>';
          else if (warns.length>0) issuesHtml = '<div class="host-issues warning">⚠️ ' + warns.map(i=>i.name).join(', ') + '</div>';
        } else if (disk.alert){
          const cls = disk.alert==='error' ? '' : ' warning';
          issuesHtml = '<div class="host-issues' + cls + '">⚠️ Disk usage ' + disk.max.toFixed(1) + '%</div>';
        }

        const os_name=(host.os_name && host.os_name!=='OS N/A')?host.os_name:'OS N/A';
        const os_release=host.os_release||'';
        const hostName=host.hostname||'Unknown';

        const serviceText=(host.service_names||[]).join(' ');
        let searchable = (hostName + ' ' + os_name + ' ' + os_release + ' ' + serviceText).toLowerCase();
        let hidden = filterText && !searchable.includes(filterText) ? 'hidden' : '';
        if (selectedSort==='os-update-needed' && !hidden){
          hidden = host.os_release ? 'hidden' : '';
        }

        hostsHtml += '<div class="host ' + cardSeverityClass + ' ' + extraCls + ' ' + hidden +
          '" onclick=\'showHostDetails(' + JSON.stringify(host) + ', "' + tenant.url + '")\'>' +
          '<div class="host-name">' + hostName + ' ' + sourceBadge + '</div>' +
          '<div class="host-status ' + (isDown?'down':'') + '"><span>' + icon + ' ' + text + '</span><span class="os-info">' + os_name + (os_release?(' '+os_release):'') + '</span></div>' +
          '<div class="host-details">CPU: ' + host.cpu + '% | Mem: ' + host.mem + '%' + diskInfo + '</div>' +
          issuesHtml +
        '</div>';
      });
      hostsHtml += '</div>';

      div.innerHTML =
        '<div class="tenant-header">' +
          '<div><div class="tenant-name" onclick="window.open(\'' + tenant.url + '\', \'_blank\')">' + tenant.tenant + '</div><div class="tenant-url">' + tenant.url + '</div></div>' +
          '<span class="status-badge ' + (issues>0?'badge-warning':'badge-ok') + '">' + hosts.length + ' hosts • ' + issues + ' issues</span>' +
        '</div>' + hostsHtml;
    }
    container.appendChild(div);
    allDisplayedHosts.push(...renderedHosts);
  });

  renderOSStats(allHosts);

  const issuesCard = document.getElementById('issues-card');
  issuesCard.className='stat-card';
  if (totalIssues>0){
    const hasError = allDisplayedHosts.some(h=>{
      const d=getDiskAlert(h);
      return (h.issues||[]).some(i=>i.led===0) || d.alert==='error';
    });
    issuesCard.classList.add(hasError?'issue-card-error':'issue-card-warn');
  } else {
    issuesCard.classList.add('issue-card-ok');
  }
  updateIssuesCardState();

  document.getElementById('total-hosts').textContent    = totalHosts;
  document.getElementById('total-services').textContent = totalServices;
  document.getElementById('issues').textContent         = totalIssues;
  document.getElementById('total-tenants').textContent  = data.length;
}

/* --------------------------------- EVENTS --------------------------------- */

document.addEventListener('DOMContentLoaded', () => {
  const logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) logoutBtn.addEventListener('click', () => { window.location.href = '/logout'; });

  initTheme();

  const sortSel = document.getElementById('sortSelect');
  if (sortSel) {
    sortSel.addEventListener('change', (e)=>{
      const sorted = sortTenants(tenantsData, e.target.value);
      renderTenantsOnly(sorted);
    });
  }

  const filterInput = document.getElementById('hostFilter');
  if (filterInput) {
    filterInput.addEventListener('input', ()=>{
      const sorted = sortTenants(tenantsData, document.getElementById('sortSelect').value);
      renderTenantsOnly(sorted);
    });
  }

  initIssuesToggle();
});

document.getElementById('modalClose').addEventListener('click', closeModal);
document.getElementById('hostModal').addEventListener('click', (e)=>{ if(e.target.id==='hostModal') closeModal(); });

/* ----------------------------- FETCH / REFRESH ----------------------------- */

function fetchDataAndRender(){
  fetch('/api/data').then(r=>r.json()).then(data=>{
    renderTenants(data);
  }).catch(err=>{
    document.getElementById('tenants').innerHTML =
      '<div class="tenant error"><div class="error-msg">Failed to load data: '+err+'</div></div>';
  });
}

fetchDataAndRender();

if (window.AUTO_REFRESH_SECONDS > 0){
  setInterval(()=>{
    fetch('/api/data').then(r=>r.json()).then(data=>{
      displayTimeInfo(data.last_fetch_time, data.refresh_interval);
      tenantsData = data.tenants;
      const sorted = sortTenants(tenantsData, document.getElementById('sortSelect').value);
      renderTenantsOnly(sorted);
    }).catch(err=>console.error('Auto-refresh failed:', err));
  }, window.AUTO_REFRESH_SECONDS * 1000);
}

/* Make modal open function available for inline onclick */
window.showHostDetails = showHostDetails;
