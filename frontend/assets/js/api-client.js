/**
 * InfraPulse AI — API Client
 * Handles all API communication with auth token management
 */

const API_BASE = '/api/v1';

class APIClient {
  constructor() {
    this.accessToken = localStorage.getItem('access_token');
    this.refreshToken = localStorage.getItem('refresh_token');
    this.currentOrgId = localStorage.getItem('current_org_id');
    this._refreshing = false;
    this._refreshPromise = null;
  }

  setTokens(accessToken, refreshToken) {
    this.accessToken = accessToken;
    this.refreshToken = refreshToken;
    localStorage.setItem('access_token', accessToken);
    if (refreshToken) localStorage.setItem('refresh_token', refreshToken);
  }

  clearTokens() {
    this.accessToken = null;
    this.refreshToken = null;
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('current_org_id');
    localStorage.removeItem('user_info');
  }

  setCurrentOrg(orgId) {
    this.currentOrgId = orgId;
    localStorage.setItem('current_org_id', orgId);
  }

  isAuthenticated() {
    return !!this.accessToken;
  }

  async _request(method, path, data = null, skipAuth = false) {
    const headers = { 'Content-Type': 'application/json' };

    if (!skipAuth && this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }

    const opts = { method, headers };
    if (data && method !== 'GET') {
      opts.body = JSON.stringify(data);
    }

    let url = path.startsWith('http') ? path : `${API_BASE}${path}`;

    let response = await fetch(url, opts);

    // Auto-refresh on 401
    if (response.status === 401 && !skipAuth && this.refreshToken) {
      if (!this._refreshing) {
        this._refreshing = true;
        this._refreshPromise = this._doRefresh();
      }
      try {
        await this._refreshPromise;
        headers['Authorization'] = `Bearer ${this.accessToken}`;
        response = await fetch(url, { ...opts, headers });
      } catch {
        this.clearTokens();
        window.location.href = '/login.html';
        throw new Error('Session expired');
      } finally {
        this._refreshing = false;
        this._refreshPromise = null;
      }
    }

    if (response.status === 401) {
      this.clearTokens();
      window.location.href = '/login.html';
      throw new Error('Unauthorized');
    }

    if (!response.ok) {
      let error;
      try { error = await response.json(); } catch { error = { detail: response.statusText }; }
      throw new APIError(error.detail || 'Request failed', response.status);
    }

    if (response.status === 204) return null;

    return response.json();
  }

  async _doRefresh() {
    const resp = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: this.refreshToken }),
    });
    if (!resp.ok) throw new Error('Refresh failed');
    const data = await resp.json();
    this.setTokens(data.access_token, data.refresh_token);
  }

  get(path) { return this._request('GET', path); }
  post(path, data) { return this._request('POST', path, data); }
  put(path, data) { return this._request('PUT', path, data); }
  patch(path, data) { return this._request('PATCH', path, data); }
  delete(path) { return this._request('DELETE', path); }

  // ── Auth ───────────────────────────────────────────────────────────────────
  async login(email, password) {
    const data = await this._request('POST', '/auth/login', { email, password }, true);
    this.setTokens(data.access_token, data.refresh_token);
    if (data.organizations?.length > 0) {
      this.setCurrentOrg(data.organizations[0].id);
    }
    localStorage.setItem('user_info', JSON.stringify({
      id: data.user_id,
      name: data.full_name,
      email: data.email,
      is_platform_admin: data.is_platform_admin,
      organizations: data.organizations,
    }));
    return data;
  }

  async register(email, password, fullName, orgName) {
    const data = await this._request('POST', '/auth/register', {
      email, password, full_name: fullName, organization_name: orgName,
    }, true);
    this.setTokens(data.access_token, data.refresh_token);
    this.setCurrentOrg(data.organization_id);
    return data;
  }

  async logout() {
    try {
      if (this.refreshToken) {
        await this._request('POST', '/auth/logout', { refresh_token: this.refreshToken });
      }
    } finally {
      this.clearTokens();
    }
  }

  // ── Dashboard ──────────────────────────────────────────────────────────────
  getDashboardOverview(orgId) {
    return this.get(`/organizations/${orgId}/dashboard/overview`);
  }

  // ── Servers ────────────────────────────────────────────────────────────────
  getServers(orgId, params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.get(`/organizations/${orgId}/servers${qs ? '?' + qs : ''}`);
  }
  getServer(orgId, serverId) { return this.get(`/organizations/${orgId}/servers/${serverId}`); }
  updateServer(orgId, serverId, data) { return this.put(`/organizations/${orgId}/servers/${serverId}`, data); }
  createAgentToken(orgId, data) { return this.post(`/organizations/${orgId}/servers/agent-tokens`, data); }
  getAgentTokens(orgId) { return this.get(`/organizations/${orgId}/servers/agent-tokens`); }

  // ── Metrics ────────────────────────────────────────────────────────────────
  getServerMetrics(orgId, serverId, metricNames, timeRange = '1h') {
    return this.get(`/organizations/${orgId}/metrics/servers/${serverId}?metric_names=${metricNames}&time_range=${timeRange}`);
  }
  getMetricsSummary(orgId) { return this.get(`/organizations/${orgId}/metrics/summary`); }

  // ── Logs ───────────────────────────────────────────────────────────────────
  searchLogs(orgId, params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.get(`/organizations/${orgId}/logs${qs ? '?' + qs : ''}`);
  }
  getLogStats(orgId, hours = 24) { return this.get(`/organizations/${orgId}/logs/stats?hours=${hours}`); }

  // ── Alerts ─────────────────────────────────────────────────────────────────
  getAlerts(orgId, params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.get(`/organizations/${orgId}/alerts${qs ? '?' + qs : ''}`);
  }
  getAlert(orgId, alertId) { return this.get(`/organizations/${orgId}/alerts/${alertId}`); }
  updateAlertStatus(orgId, alertId, status, notes = '') {
    return this.put(`/organizations/${orgId}/alerts/${alertId}/status`, { status, resolution_notes: notes });
  }
  getAlertStats(orgId) { return this.get(`/organizations/${orgId}/alerts/stats/summary`); }
  getAlertRules(orgId) { return this.get(`/organizations/${orgId}/alerts/rules`); }
  createAlertRule(orgId, data) { return this.post(`/organizations/${orgId}/alerts/rules`, data); }

  // ── Incidents ──────────────────────────────────────────────────────────────
  getIncidents(orgId, params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.get(`/organizations/${orgId}/incidents${qs ? '?' + qs : ''}`);
  }
  createIncident(orgId, data) { return this.post(`/organizations/${orgId}/incidents`, data); }
  updateIncident(orgId, incidentId, data) { return this.put(`/organizations/${orgId}/incidents/${incidentId}`, data); }

  // ── Proxmox ────────────────────────────────────────────────────────────────
  getProxmoxConnections(orgId) { return this.get(`/organizations/${orgId}/proxmox/connections`); }
  createProxmoxConnection(orgId, data) { return this.post(`/organizations/${orgId}/proxmox/connections`, data); }
  testProxmoxConnection(orgId, connId) { return this.post(`/organizations/${orgId}/proxmox/connections/${connId}/test`); }
  syncProxmoxConnection(orgId, connId) { return this.post(`/organizations/${orgId}/proxmox/connections/${connId}/sync`); }
  getProxmoxNodes(orgId, connId) { return this.get(`/organizations/${orgId}/proxmox/connections/${connId}/nodes`); }
  getProxmoxVMs(orgId, connId, vmType = '') {
    return this.get(`/organizations/${orgId}/proxmox/connections/${connId}/vms${vmType ? '?vm_type=' + vmType : ''}`);
  }

  // ── AI Operations ──────────────────────────────────────────────────────────
  analyzeAlert(orgId, alertId) { return this.post(`/organizations/${orgId}/ai/analyze-alert/${alertId}`); }
  analyzeServer(orgId, serverId) { return this.post(`/organizations/${orgId}/ai/analyze-server/${serverId}`); }
  analyzeIncident(orgId, incidentId) { return this.post(`/organizations/${orgId}/ai/analyze-incident/${incidentId}`); }
  getAIAnalyses(orgId) { return this.get(`/organizations/${orgId}/ai/analyses`); }
  getAIConfig(orgId) { return this.get(`/organizations/${orgId}/ai/config`); }
  updateAIConfig(orgId, config) { return this.put(`/organizations/${orgId}/ai/config`, config); }

  // ── Notifications ──────────────────────────────────────────────────────────
  getNotificationChannels(orgId) { return this.get(`/organizations/${orgId}/notifications/channels`); }
  createNotificationChannel(orgId, data) { return this.post(`/organizations/${orgId}/notifications/channels`, data); }
  testNotificationChannel(orgId, channelId) { return this.post(`/organizations/${orgId}/notifications/channels/${channelId}/test`); }
  updateNotificationChannel(orgId, channelId, data) { return this.put(`/organizations/${orgId}/notifications/channels/${channelId}`, data); }
  deleteNotificationChannel(orgId, channelId) { return this.delete(`/organizations/${orgId}/notifications/channels/${channelId}`); }
  getNotificationPolicies(orgId) { return this.get(`/organizations/${orgId}/notifications/policies`); }
  createNotificationPolicy(orgId, data) { return this.post(`/organizations/${orgId}/notifications/policies`, data); }
  updateNotificationPolicy(orgId, policyId, data) { return this.put(`/organizations/${orgId}/notifications/policies/${policyId}`, data); }
  deleteNotificationPolicy(orgId, policyId) { return this.delete(`/organizations/${orgId}/notifications/policies/${policyId}`); }

  // ── Organizations ──────────────────────────────────────────────────────────
  getOrganizations() { return this.get('/organizations'); }
  getOrganization(orgId) { return this.get(`/organizations/${orgId}`); }
  updateOrganization(orgId, data) { return this.put(`/organizations/${orgId}`, data); }
  getMembers(orgId) { return this.get(`/organizations/${orgId}/members`); }
  inviteUser(orgId, email, role) { return this.post(`/organizations/${orgId}/invite`, { email, role }); }
  getOnboarding(orgId) { return this.get(`/organizations/${orgId}/onboarding`); }

  // ── Current user ───────────────────────────────────────────────────────────
  getCurrentUser() { return this.get('/users/me'); }
  updateCurrentUser(data) { return this.put('/users/me', data); }
}

class APIError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

// Global API client instance
window.api = new APIClient();

// ── Utility functions ────────────────────────────────────────────────────────
function showToast(message, type = 'info', duration = 4000) {
  const icons = { success: '✓', error: '✗', warning: '⚠', info: 'ℹ' };
  const container = document.getElementById('toast-container') || (() => {
    const el = document.createElement('div');
    el.id = 'toast-container';
    el.className = 'toast-container';
    document.body.appendChild(el);
    return el;
  })();

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || 'ℹ'}</span>
    <span class="toast-message">${message}</span>
  `;
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; toast.style.transform = 'translateX(100%)'; toast.style.transition = '0.3s ease'; setTimeout(() => toast.remove(), 300); }, duration);
}

function formatBytes(bytes, decimals = 1) {
  if (!bytes) return '0 B';
  const k = 1024, dm = decimals;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

function formatUptime(seconds) {
  if (!seconds) return 'N/A';
  const d = Math.floor(seconds / 86400), h = Math.floor((seconds % 86400) / 3600), m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function formatRelativeTime(dateStr) {
  const date = new Date(dateStr);
  const diff = (Date.now() - date) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
  return `${Math.floor(diff/86400)}d ago`;
}

function getHealthClass(score) {
  if (score >= 90) return 'excellent';
  if (score >= 70) return 'good';
  if (score >= 50) return 'fair';
  if (score >= 25) return 'poor';
  return 'critical';
}

function getProgressColor(pct) {
  if (pct >= 90) return 'red';
  if (pct >= 75) return 'amber';
  return 'green';
}

function getSeverityBadge(severity) {
  return `<span class="badge badge-${severity}">${severity}</span>`;
}

function getStatusBadge(status) {
  return `<span class="badge badge-${status}">${status}</span>`;
}

function requireAuth() {
  if (!window.api.isAuthenticated()) {
    window.location.href = '/login.html';
    return false;
  }
  return true;
}

function getCurrentOrg() {
  return localStorage.getItem('current_org_id');
}

function getUserInfo() {
  try { return JSON.parse(localStorage.getItem('user_info') || '{}'); } catch { return {}; }
}

function initSidebar() {
  const user = getUserInfo();
  document.querySelectorAll('.user-name').forEach(el => el.textContent = user.name || 'User');
  document.querySelectorAll('.user-avatar').forEach(el => el.textContent = (user.name || 'U')[0].toUpperCase());

  // Set active nav item
  const path = window.location.pathname;
  document.querySelectorAll('.nav-item').forEach(el => {
    const href = el.getAttribute('href');
    if (href && path.includes(href.split('.')[0].replace('/','').split('/')[0])) {
      el.classList.add('active');
    }
  });

  // Logout
  document.querySelector('.logout-btn')?.addEventListener('click', async () => {
    await window.api.logout();
    window.location.href = '/login.html';
  });

  // Mobile sidebar toggle
  document.getElementById('sidebar-toggle')?.addEventListener('click', () => {
    document.querySelector('.sidebar').classList.toggle('open');
  });
}
