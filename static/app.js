/* ═══════════════════════════════════════════════════════════════
   TaskPulse — frontend logic
═══════════════════════════════════════════════════════════════ */

// ── State ──────────────────────────────────────────────────────
let tasks        = [];
let editingId    = null;
let deleteId     = null;
let currentView  = 'all';
let currentPri   = 'all';
let currentCat   = 'all';
let searchQuery  = '';
let sortMode     = 'newest';
let firedAlarms  = new Set(JSON.parse(localStorage.getItem('firedAlarms') || '[]'));

// ── Category metadata ──────────────────────────────────────────
const CAT_META = {
  general:   { emoji: '📋', color: '#747d8c', label: 'General' },
  work:      { emoji: '💼', color: '#5352ed', label: 'Work' },
  personal:  { emoji: '👤', color: '#ff6b81', label: 'Personal' },
  shopping:  { emoji: '🛒', color: '#26de81', label: 'Shopping' },
  health:    { emoji: '❤️', color: '#45aaf2', label: 'Health' },
  finance:   { emoji: '💰', color: '#fd9644', label: 'Finance' },
  education: { emoji: '📚', color: '#a55eea', label: 'Education' },
};

const PRI_ORDER = { high: 0, medium: 1, low: 2, none: 3 };

// ── DOM refs ───────────────────────────────────────────────────
const $ = id => document.getElementById(id);

// ── Init ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadTheme();
  setupListeners();
  loadTasks();
  startAlarmChecker();
  requestNotifPermission();
});

// ═══════════════════════════════════════════════════════════════
// API
// ═══════════════════════════════════════════════════════════════
async function loadTasks() {
  try {
    const r = await fetch('/api/tasks');
    tasks = await r.json();
    render();
  } catch (e) {
    toast('Failed to load tasks', 'error');
  }
}

async function apiCreate(data) {
  const r = await fetch('/api/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error((await r.json()).error || 'Error');
  return r.json();
}

async function apiUpdate(id, data) {
  const r = await fetch(`/api/tasks/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error('Update failed');
  return r.json();
}

async function apiDelete(id) {
  const r = await fetch(`/api/tasks/${id}`, { method: 'DELETE' });
  if (!r.ok) throw new Error('Delete failed');
}

// ═══════════════════════════════════════════════════════════════
// FILTERING / SORTING
// ═══════════════════════════════════════════════════════════════
function getFiltered() {
  const today = todayStr();
  let list = tasks.filter(t => {
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      if (!t.title.toLowerCase().includes(q) && !t.description.toLowerCase().includes(q)) return false;
    }
    if (currentPri !== 'all' && t.priority !== currentPri) return false;
    if (currentCat !== 'all' && t.category !== currentCat) return false;

    switch (currentView) {
      case 'today':
        return t.due_date === today && !t.completed;
      case 'upcoming':
        return t.due_date && t.due_date > today && !t.completed;
      case 'overdue':
        return t.due_date && t.due_date < today && !t.completed;
      case 'completed':
        return !!t.completed;
      default:
        return true;
    }
  });

  list.sort((a, b) => {
    switch (sortMode) {
      case 'oldest':   return a.id - b.id;
      case 'due_asc':  return cmpDate(a.due_date, b.due_date, true);
      case 'due_desc': return cmpDate(a.due_date, b.due_date, false);
      case 'priority': return (PRI_ORDER[a.priority] ?? 3) - (PRI_ORDER[b.priority] ?? 3);
      case 'alpha':    return a.title.localeCompare(b.title);
      default:         return b.id - a.id; // newest
    }
  });

  return list;
}

function cmpDate(a, b, asc) {
  if (!a && !b) return 0;
  if (!a) return asc ? 1 : -1;
  if (!b) return asc ? -1 : 1;
  return asc ? a.localeCompare(b) : b.localeCompare(a);
}

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

// ═══════════════════════════════════════════════════════════════
// RENDER
// ═══════════════════════════════════════════════════════════════
function render() {
  renderBadges();
  renderCategoryFilters();
  renderStats();
  renderProgress();
  renderTasks();
}

function renderBadges() {
  const today = todayStr();
  const active = tasks.filter(t => !t.completed);

  $('badge-all').textContent       = tasks.length;
  $('badge-today').textContent     = tasks.filter(t => t.due_date === today && !t.completed).length;
  $('badge-upcoming').textContent  = tasks.filter(t => t.due_date && t.due_date > today && !t.completed).length;
  $('badge-overdue').textContent   = tasks.filter(t => t.due_date && t.due_date < today && !t.completed).length;
  $('badge-completed').textContent = tasks.filter(t => t.completed).length;
}

function renderStats() {
  const done    = tasks.filter(t => t.completed).length;
  const pending = tasks.filter(t => !t.completed).length;
  $('stat-total').textContent   = tasks.length;
  $('stat-done').textContent    = done;
  $('stat-pending').textContent = pending;
}

function renderProgress() {
  const total   = tasks.length;
  const done    = tasks.filter(t => t.completed).length;
  const pct     = total ? Math.round((done / total) * 100) : 0;
  $('progText').textContent = `${done} of ${total} completed`;
  $('progPct').textContent  = `${pct}%`;
  $('progFill').style.width = `${pct}%`;
}

function renderCategoryFilters() {
  const counts = {};
  tasks.forEach(t => { counts[t.category] = (counts[t.category] || 0) + 1; });

  const wrap = $('categoryFilters');
  wrap.innerHTML = '';

  const allBtn = makeEl('button', 'cat-btn' + (currentCat === 'all' ? ' active' : ''));
  allBtn.dataset.cat = 'all';
  allBtn.innerHTML = `<span class="cat-dot" style="background:#6c63ff"></span>
                      <span class="cat-name">All</span>
                      <span class="cat-count">${tasks.length}</span>`;
  allBtn.addEventListener('click', () => setCat('all'));
  wrap.appendChild(allBtn);

  Object.entries(counts).forEach(([cat, cnt]) => {
    const meta = CAT_META[cat] || CAT_META.general;
    const btn  = makeEl('button', 'cat-btn' + (currentCat === cat ? ' active' : ''));
    btn.dataset.cat = cat;
    btn.innerHTML = `<span class="cat-dot" style="background:${meta.color}"></span>
                     <span class="cat-name">${meta.emoji} ${meta.label}</span>
                     <span class="cat-count">${cnt}</span>`;
    btn.addEventListener('click', () => setCat(cat));
    wrap.appendChild(btn);
  });
}

function renderTasks() {
  const list    = getFiltered();
  const taskEl  = $('taskList');
  const emptyEl = $('emptyState');

  if (list.length === 0) {
    emptyEl.style.display = '';
    // Remove old cards only
    [...taskEl.children].forEach(c => { if (c.id !== 'emptyState') c.remove(); });
    return;
  }

  emptyEl.style.display = 'none';
  [...taskEl.children].forEach(c => { if (c.id !== 'emptyState') c.remove(); });

  list.forEach(t => {
    taskEl.appendChild(buildCard(t));
  });
}

function buildCard(t) {
  const today    = todayStr();
  const overdue  = t.due_date && t.due_date < today && !t.completed;
  const hasAlarm = !!t.alarm_time;

  const card = makeEl('div', 'task-card' +
    (t.completed ? ' done' : '') +
    (overdue     ? ' overdue' : '') +
    (hasAlarm    ? ' has-alarm' : ''));

  card.dataset.id       = t.id;
  card.dataset.priority = t.priority || 'none';

  // Alarm pulse dot
  const alarmDot = makeEl('div', 'alarm-indicator');
  alarmDot.title = 'Alarm set';
  card.appendChild(alarmDot);

  // Checkbox
  const chk = makeEl('button', 'task-check' + (t.completed ? ' checked' : ''));
  chk.innerHTML = '<i class="fas fa-check"></i>';
  chk.title = t.completed ? 'Mark incomplete' : 'Mark complete';
  chk.addEventListener('click', () => toggleComplete(t));
  card.appendChild(chk);

  // Body
  const body = makeEl('div', 'task-body');

  const title = makeEl('div', 'task-title');
  title.textContent = t.title;
  body.appendChild(title);

  if (t.description) {
    const desc = makeEl('div', 'task-desc');
    desc.textContent = t.description;
    body.appendChild(desc);
  }

  // Meta row
  const meta = makeEl('div', 'task-meta');

  const priBadge = makeEl('span', `badge badge-priority-${t.priority || 'none'}`);
  priBadge.innerHTML = `<span class="dot ${t.priority || 'none'}"></span> ${capitalize(t.priority || 'none')}`;
  meta.appendChild(priBadge);

  const catMeta = CAT_META[t.category] || CAT_META.general;
  const catBadge = makeEl('span', `badge badge-cat badge-cat-${t.category || 'general'}`);
  catBadge.textContent = `${catMeta.emoji} ${catMeta.label}`;
  meta.appendChild(catBadge);

  if (t.due_date) {
    const due = makeEl('span', 'task-due');
    due.innerHTML = `<i class="fas fa-calendar-alt"></i> ${formatDate(t.due_date)}`;
    if (overdue) due.title = 'Overdue!';
    meta.appendChild(due);
  }

  if (t.alarm_time) {
    const alm = makeEl('span', 'task-alarm');
    alm.innerHTML = `<i class="fas fa-bell"></i> ${formatDatetime(t.alarm_time)}`;
    meta.appendChild(alm);
  }

  if (t.gcal_event_id) {
    const gcal = makeEl('span', 'gcal-badge');
    gcal.innerHTML = '<i class="fab fa-google"></i>';
    gcal.title = 'Synced to Google Calendar';
    meta.appendChild(gcal);
  }

  body.appendChild(meta);
  card.appendChild(body);

  // Actions
  const acts = makeEl('div', 'task-actions');

  const editBtn = makeEl('button', 'act-btn');
  editBtn.title = 'Edit';
  editBtn.innerHTML = '<i class="fas fa-pen"></i>';
  editBtn.addEventListener('click', () => openEdit(t));
  acts.appendChild(editBtn);

  const delBtn = makeEl('button', 'act-btn del-btn');
  delBtn.title = 'Delete';
  delBtn.innerHTML = '<i class="fas fa-trash"></i>';
  delBtn.addEventListener('click', () => openConfirmDelete(t));
  acts.appendChild(delBtn);

  card.appendChild(acts);
  return card;
}

// ═══════════════════════════════════════════════════════════════
// EVENT LISTENERS
// ═══════════════════════════════════════════════════════════════
function setupListeners() {
  // Sidebar nav
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => setView(btn.dataset.view));
  });

  // Priority filter
  document.querySelectorAll('.pf-btn').forEach(btn => {
    btn.addEventListener('click', () => setPriority(btn.dataset.priority));
  });

  // Search
  $('searchInput').addEventListener('input', e => {
    searchQuery = e.target.value.trim();
    render();
  });

  // Sort
  $('sortSel').addEventListener('change', e => {
    sortMode = e.target.value;
    render();
  });

  // Add task
  $('addBtn').addEventListener('click', openAdd);

  // Sidebar toggle
  $('sidebarToggle').addEventListener('click', toggleSidebar);

  // Theme
  $('themeBtn').addEventListener('click', toggleTheme);

  // Notification button
  $('notifBtn').addEventListener('click', requestNotifPermission);

  // Modal controls
  $('modalClose').addEventListener('click', closeModal);
  $('cancelBtn').addEventListener('click', closeModal);
  $('saveBtn').addEventListener('click', saveTask);
  $('overlay').addEventListener('click', e => { if (e.target === $('overlay')) closeModal(); });

  // Confirm delete
  $('confirmClose').addEventListener('click', closeConfirm);
  $('confirmNo').addEventListener('click', closeConfirm);
  $('confirmYes').addEventListener('click', confirmDelete);
  $('confirmOverlay').addEventListener('click', e => { if (e.target === $('confirmOverlay')) closeConfirm(); });

  // Keyboard
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closeModal(); closeConfirm(); }
    if (e.key === 'Enter' && $('overlay').classList.contains('open')) {
      if (document.activeElement.tagName !== 'TEXTAREA') saveTask();
    }
  });
}

// ═══════════════════════════════════════════════════════════════
// VIEW / FILTER HELPERS
// ═══════════════════════════════════════════════════════════════
function setView(v) {
  currentView = v;
  document.querySelectorAll('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.view === v));
  const labels = {
    all: ['All Tasks', 'All your tasks in one place'],
    today: ['Today', "Tasks due today"],
    upcoming: ['Upcoming', 'Tasks due in the future'],
    overdue: ['Overdue', 'Tasks past their due date'],
    completed: ['Completed', 'Tasks you\'ve finished'],
  };
  $('viewTitle').textContent = labels[v][0];
  $('viewSub').textContent   = labels[v][1];
  render();
}

function setPriority(p) {
  currentPri = p;
  document.querySelectorAll('.pf-btn').forEach(b => b.classList.toggle('active', b.dataset.priority === p));
  render();
}

function setCat(c) {
  currentCat = c;
  render(); // category filters re-render inside render()
}

// ═══════════════════════════════════════════════════════════════
// MODAL (ADD / EDIT)
// ═══════════════════════════════════════════════════════════════
function openAdd() {
  editingId = null;
  $('modalTitle').textContent = 'New Task';
  $('saveBtn').innerHTML = '<i class="fas fa-plus"></i> Add Task';
  clearForm();
  $('overlay').classList.add('open');
  setTimeout(() => $('fTitle').focus(), 80);
}

function openEdit(t) {
  editingId = t.id;
  $('modalTitle').textContent = 'Edit Task';
  $('saveBtn').innerHTML = '<i class="fas fa-floppy-disk"></i> Save Changes';
  $('fTitle').value    = t.title;
  $('fDesc').value     = t.description || '';
  $('fPriority').value = t.priority || 'medium';
  $('fCategory').value = t.category || 'general';
  $('fDue').value      = t.due_date || '';
  $('fAlarm').value    = t.alarm_time || '';
  $('overlay').classList.add('open');
  setTimeout(() => $('fTitle').focus(), 80);
}

function closeModal() {
  $('overlay').classList.remove('open');
  editingId = null;
}

function clearForm() {
  $('fTitle').value    = '';
  $('fDesc').value     = '';
  $('fPriority').value = 'medium';
  $('fCategory').value = 'general';
  $('fDue').value      = '';
  $('fAlarm').value    = '';
}

async function saveTask() {
  const title = $('fTitle').value.trim();
  if (!title) {
    $('fTitle').focus();
    $('fTitle').style.borderColor = 'var(--danger)';
    setTimeout(() => $('fTitle').style.borderColor = '', 1500);
    toast('Please enter a title', 'error');
    return;
  }

  const payload = {
    title,
    description: $('fDesc').value.trim(),
    priority:    $('fPriority').value,
    category:    $('fCategory').value,
    due_date:    $('fDue').value,
    alarm_time:  $('fAlarm').value,
  };

  try {
    if (editingId) {
      const updated = await apiUpdate(editingId, payload);
      tasks = tasks.map(t => t.id === editingId ? updated : t);
      toast('Task updated', 'success');
    } else {
      const created = await apiCreate(payload);
      tasks.unshift(created);
      toast('Task added', 'success');
    }
    closeModal();
    render();
  } catch (e) {
    toast(e.message || 'Something went wrong', 'error');
  }
}

// ═══════════════════════════════════════════════════════════════
// COMPLETE TOGGLE
// ═══════════════════════════════════════════════════════════════
async function toggleComplete(t) {
  try {
    const updated = await apiUpdate(t.id, { completed: t.completed ? 0 : 1 });
    tasks = tasks.map(x => x.id === t.id ? updated : x);
    toast(updated.completed ? '✓ Task completed!' : 'Task reopened', updated.completed ? 'success' : 'info');
    render();
  } catch {
    toast('Failed to update task', 'error');
  }
}

// ═══════════════════════════════════════════════════════════════
// DELETE
// ═══════════════════════════════════════════════════════════════
function openConfirmDelete(t) {
  deleteId = t.id;
  $('confirmTaskName').textContent = `"${t.title}"`;
  $('confirmOverlay').classList.add('open');
}

function closeConfirm() {
  $('confirmOverlay').classList.remove('open');
  deleteId = null;
}

async function confirmDelete() {
  if (!deleteId) return;
  try {
    await apiDelete(deleteId);
    tasks = tasks.filter(t => t.id !== deleteId);
    toast('Task deleted', 'warning');
    closeConfirm();
    render();
  } catch {
    toast('Failed to delete task', 'error');
  }
}

// ═══════════════════════════════════════════════════════════════
// ALARMS & NOTIFICATIONS
// ═══════════════════════════════════════════════════════════════
function requestNotifPermission() {
  if (!('Notification' in window)) return;
  Notification.requestPermission().then(p => {
    $('notifDot').classList.toggle('active', p === 'granted');
    if (p === 'granted') toast('Notifications enabled', 'success');
    else if (p === 'denied') toast('Notifications blocked by browser', 'warning');
  });
}

function startAlarmChecker() {
  checkAlarms();
  setInterval(checkAlarms, 30000); // every 30 s
}

function checkAlarms() {
  const now     = new Date();
  const nowMin  = now.toISOString().slice(0, 16); // "2026-04-27T15:30"

  tasks.forEach(t => {
    if (!t.alarm_time || t.completed) return;
    if (firedAlarms.has(String(t.id))) return;

    const alarmMin = t.alarm_time.slice(0, 16);

    // Fire if alarm is within the current minute
    if (alarmMin === nowMin) {
      fireAlarm(t);
    }

    // Also fire if alarm was in the past 2 minutes but hasn't fired yet
    // (covers the case where app was just opened)
    const diff = (now - new Date(t.alarm_time)) / 1000;
    if (diff >= 0 && diff < 120) {
      fireAlarm(t);
    }
  });
}

function fireAlarm(t) {
  if (firedAlarms.has(String(t.id))) return;
  firedAlarms.add(String(t.id));
  localStorage.setItem('firedAlarms', JSON.stringify([...firedAlarms]));

  // In-app toast
  toast(`⏰ Alarm: ${t.title}`, 'alarm', 6000);

  // Browser notification
  if (Notification.permission === 'granted') {
    const n = new Notification(`⏰ TaskPulse Reminder`, {
      body: t.title + (t.description ? `\n${t.description}` : ''),
      icon: '/static/icon.png',
      tag:  `task-${t.id}`,
    });
    n.onclick = () => { window.focus(); n.close(); };
    setTimeout(() => n.close(), 8000);
  }
}

// ═══════════════════════════════════════════════════════════════
// THEME
// ═══════════════════════════════════════════════════════════════
function loadTheme() {
  const saved = localStorage.getItem('theme') || 'dark';
  document.documentElement.dataset.theme = saved;
  $('themeIcon').className = saved === 'dark' ? 'fas fa-moon' : 'fas fa-sun';
}

function toggleTheme() {
  const current = document.documentElement.dataset.theme;
  const next    = current === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem('theme', next);
  $('themeIcon').className = next === 'dark' ? 'fas fa-moon' : 'fas fa-sun';
}

// ═══════════════════════════════════════════════════════════════
// SIDEBAR
// ═══════════════════════════════════════════════════════════════
function toggleSidebar() {
  const sb = $('sidebar');
  if (window.innerWidth <= 768) {
    sb.classList.toggle('mobile-open');
  } else {
    sb.classList.toggle('collapsed');
  }
}

// ═══════════════════════════════════════════════════════════════
// TOASTS
// ═══════════════════════════════════════════════════════════════
const TOAST_ICONS = {
  success: 'fa-circle-check',
  error:   'fa-circle-xmark',
  warning: 'fa-triangle-exclamation',
  info:    'fa-circle-info',
  alarm:   'fa-bell',
};

function toast(message, type = 'info', duration = 3500) {
  const wrap   = $('toastWrap');
  const el     = makeEl('div', `toast ${type}`);
  const icon   = TOAST_ICONS[type] || 'fa-circle-info';
  el.innerHTML = `<i class="fas ${icon}"></i><span>${message}</span>`;
  wrap.appendChild(el);

  setTimeout(() => {
    el.classList.add('out');
    setTimeout(() => el.remove(), 280);
  }, duration);
}

// ═══════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════
function makeEl(tag, cls = '') {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  return el;
}

function capitalize(s) {
  return s ? s[0].toUpperCase() + s.slice(1) : '';
}

function formatDate(d) {
  if (!d) return '';
  const [y, m, day] = d.split('-');
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${months[+m - 1]} ${+day}, ${y}`;
}

function formatDatetime(dt) {
  if (!dt) return '';
  const d     = new Date(dt);
  const date  = formatDate(dt.slice(0, 10));
  const hrs   = d.getHours();
  const mins  = String(d.getMinutes()).padStart(2, '0');
  const ampm  = hrs >= 12 ? 'PM' : 'AM';
  const h12   = hrs % 12 || 12;
  return `${date} ${h12}:${mins} ${ampm}`;
}
