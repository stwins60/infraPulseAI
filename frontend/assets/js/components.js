/**
 * InfraPulse AI — Shared UI Components
 * Renders sidebar, org switcher, user bar for all pages
 */

const NAV_ITEMS = [
  { section: 'Overview', items: [
    { href: '/dashboard.html', icon: '🏠', label: 'Overview', key: 'dashboard' },
  ]},
  { section: 'Infrastructure', items: [
    { href: '/infrastructure.html', icon: '🗄️', label: 'Inventory', key: 'infrastructure' },
    { href: '/proxmox.html', icon: '🖥️', label: 'Proxmox', key: 'proxmox' },
    { href: '/servers.html', icon: '💻', label: 'Servers', key: 'servers' },
  ]},
  { section: 'Observability', items: [
    { href: '/logs.html', icon: '📋', label: 'Logs', key: 'logs' },
    { href: '/alerts.html', icon: '🔔', label: 'Alerts', key: 'alerts' },
    { href: '/incidents.html', icon: '🚨', label: 'Incidents', key: 'incidents' },
  ]},
  { section: 'Intelligence', items: [
    { href: '/ai-ops.html', icon: '🤖', label: 'AI Operations', key: 'ai-ops' },
  ]},
  { section: 'Configuration', items: [
    { href: '/notifications.html', icon: '📢', label: 'Notifications', key: 'notifications' },
    { href: '/team.html', icon: '👥', label: 'Team', key: 'team' },
    { href: '/settings.html', icon: '⚙️', label: 'Settings', key: 'settings' },
  ]},
];

function renderSidebar(activeKey) {
  const user = getUserInfo();
  const orgs = user.organizations || [];
  const currentOrgId = getCurrentOrg();

  const navHtml = NAV_ITEMS.map(section => `
    <div class="nav-section">
      <div class="nav-section-label">${section.section}</div>
      ${section.items.map(item => `
        <a href="${item.href}" class="nav-item${item.key === activeKey ? ' active' : ''}">
          <span class="nav-icon">${item.icon}</span> ${item.label}
        </a>
      `).join('')}
    </div>
  `).join('');

  const orgOptions = orgs.map(o =>
    `<option value="${o.id}" ${o.id === currentOrgId ? 'selected' : ''}>${o.name}</option>`
  ).join('');

  return `
    <div class="sidebar-logo">
      <div class="logo-icon">⚡</div>
      <div>
        <div class="logo-text">InfraPulse AI</div>
        <div class="logo-sub">Observability Platform</div>
      </div>
    </div>
    ${orgs.length > 0 ? `
    <div class="org-switcher">
      <select id="org-select">${orgOptions}</select>
    </div>` : ''}
    <nav>${navHtml}</nav>
    <div class="sidebar-footer">
      <div class="user-info">
        <div class="user-avatar" id="user-avatar">${(user.name || 'U')[0].toUpperCase()}</div>
        <div>
          <div class="user-name" id="user-name">${user.name || 'User'}</div>
          <div class="user-role">Member</div>
        </div>
      </div>
      <button class="btn btn-secondary btn-sm logout-btn" style="width:100%;margin-top:8px;justify-content:center;" id="logout-btn">Sign Out</button>
    </div>
  `;
}

function initPage(activeKey, titleText, subtitleText) {
  if (!requireAuth()) return false;

  // Render sidebar
  const sidebar = document.querySelector('.sidebar');
  if (sidebar) sidebar.innerHTML = renderSidebar(activeKey);

  // Org switcher handler
  document.getElementById('org-select')?.addEventListener('change', e => {
    window.api.setCurrentOrg(e.target.value);
    window.location.reload();
  });

  // Logout
  document.getElementById('logout-btn')?.addEventListener('click', async () => {
    await window.api.logout();
    window.location.href = '/login.html';
  });

  // Set page title
  if (titleText) {
    const el = document.querySelector('.page-title');
    if (el) el.textContent = titleText;
  }
  if (subtitleText) {
    const el = document.querySelector('.page-subtitle');
    if (el) el.textContent = subtitleText;
  }

  return true;
}

// Standard page shell generator (for pages that use the same layout pattern)
function pageShell(activeKey, title, subtitle, topbarActionsHtml, bodyHtml) {
  return `
<div class="app-layout">
  <aside class="sidebar"></aside>
  <div class="main-content">
    <div class="topbar">
      <div>
        <div class="page-title">${title}</div>
        <div class="page-subtitle">${subtitle}</div>
      </div>
      <div class="topbar-actions">${topbarActionsHtml || ''}</div>
    </div>
    <div class="page-content">${bodyHtml}</div>
  </div>
</div>
<div id="toast-container" class="toast-container"></div>
  `;
}
