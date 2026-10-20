// Projects: groups of chats that can keep their memories and documents to
// themselves. Server rules: src/folder_memory.py and src/folder_documents.py.
// Data still lives in a chat's `folder` field; "project" is the name shown to
// people. Chats outside any project are in "Main", which sees everything
// except what compartmentalized projects keep to themselves.
import uiModule from './ui.js?v=20260916largetoolscroll1';

const API_BASE = window.location.origin;

// What a compartmentalized project starts with from Main's memories.
export const MEMORY_START_OPTIONS = [
  {
    id: 'fresh', receive: 'none',
    label: 'Start fresh',
    description: 'No memories from Main.',
  },
  {
    id: 'frozen', receive: 'snapshot',
    label: "Start with today's memories",
    description: 'Knows what Main remembers now, but nothing Main learns later.',
  },
  {
    id: 'flowing', receive: 'all',
    label: 'Keep receiving Main’s memories',
    description: 'Sees Main’s memories, including new ones.',
  },
];

// Older policies stored a memory mode; the dialog shows them as settings.
export function settingsFor(project) {
  const memory = (project && project.memory) || {};
  const contained = memory.share === false;
  const start = MEMORY_START_OPTIONS.find(o => o.receive === (memory.receive || 'all'))
    || MEMORY_START_OPTIONS[MEMORY_START_OPTIONS.length - 1];
  return {
    memoryContained: contained,
    memoryStart: contained ? start.id : 'fresh',
    documentsContained: !!(project && project.documents_private),
  };
}

export function describeSettings(project) {
  const s = settingsFor(project);
  const parts = [];
  if (s.memoryContained) parts.push('own memory');
  if (s.documentsContained) parts.push('own documents');
  return parts.length ? parts.join(', ') : 'shares with Main';
}

let _projects = [];
let _sessions = null; // { setProjectGroupSource, renderSessionList, loadSessions }

export function knownProjectNames() {
  return _projects.map(p => p.name);
}

export async function refreshProjects() {
  try {
    const res = await fetch(`${API_BASE}/api/folders`, { credentials: 'same-origin' });
    if (!res.ok) return _projects;
    const data = await res.json();
    _projects = (Array.isArray(data.folders) ? data.folders : []).filter(p => p.name !== 'Assistant');
  } catch (_) { /* keep the last known list */ }
  if (_sessions) _sessions.renderSessionList();
  return _projects;
}

async function saveProjectSettings(name, settings) {
  const start = MEMORY_START_OPTIONS.find(o => o.id === settings.memoryStart) || MEMORY_START_OPTIONS[0];
  const res = await fetch(`${API_BASE}/api/folders/${encodeURIComponent(name)}/settings`, {
    method: 'PUT',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      receive: settings.memoryContained ? start.receive : 'all',
      share: !settings.memoryContained,
      documents_private: !!settings.documentsContained,
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function renameProject(oldName, newName) {
  const res = await fetch(`${API_BASE}/api/folders/${encodeURIComponent(oldName)}/rename`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_name: newName }),
  });
  if (!res.ok) throw new Error(await res.text());
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

// A modal in the same shape as styledConfirm. `build(body, footer, close)` fills it.
function openDialog({ title, build }) {
  return new Promise(resolve => {
    const overlay = el('div', 'modal project-dialog-overlay');
    const box = el('div', 'modal-content styled-confirm-box project-dialog');
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    const header = el('div', 'modal-header');
    const h = el('h4', null, title);
    h.id = `project-dialog-title-${Date.now()}`;
    box.setAttribute('aria-labelledby', h.id);
    header.appendChild(h);
    const body = el('div', 'modal-body');
    const footer = el('div', 'modal-footer');
    box.append(header, body, footer);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    const prevFocus = document.activeElement;
    function close(result) {
      document.removeEventListener('keydown', onKey, true);
      overlay.remove();
      try { prevFocus && prevFocus.focus && prevFocus.focus(); } catch (_) {}
      resolve(result);
    }
    function onKey(e) {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(null); }
    }
    overlay.addEventListener('click', e => { if (e.target === overlay) close(null); });
    document.addEventListener('keydown', onKey, true);
    build(body, footer, close);
  });
}

function checkboxRow(label, description, checked) {
  const row = el('label', 'project-option');
  const box = el('input');
  box.type = 'checkbox';
  box.checked = !!checked;
  const text = el('span', 'project-option-text');
  text.append(el('span', 'project-option-label', label), el('span', 'project-option-desc', description));
  row.append(box, text);
  return { row, box };
}

/**
 * The project dialog: name, compartmentalized memory (with what it starts
 * from) and compartmentalized documents. Resolves to { name, settings } or
 * null when cancelled.
 */
// A new project starts compartmentalized: its own memory, starting fresh,
// and its own documents.
const NEW_PROJECT_SETTINGS = { memoryContained: true, memoryStart: 'fresh', documentsContained: true };

export function chooseProjectSettings({ title, name = '', project = null, confirmText = 'Save' } = {}) {
  const current = project ? settingsFor(project) : { ...NEW_PROJECT_SETTINGS };
  return openDialog({
    title,
    build(body, footer, close) {
      const nameInput = el('input', 'settings-input project-name-input');
      nameInput.type = 'text';
      nameInput.placeholder = 'Project name, e.g. Homework';
      nameInput.value = name;
      nameInput.setAttribute('aria-label', 'Project name');
      body.appendChild(nameInput);

      const memory = checkboxRow(
        'Compartmentalized memory',
        'What this project remembers stays in this project.',
        current.memoryContained,
      );
      body.appendChild(memory.row);
      const startList = el('div', 'project-start-list');
      startList.setAttribute('role', 'radiogroup');
      startList.setAttribute('aria-label', 'What this project starts with');
      const radioName = `project-memory-start-${Date.now()}`;
      MEMORY_START_OPTIONS.forEach(option => {
        const row = el('label', 'project-option project-start-option');
        const radio = el('input');
        radio.type = 'radio';
        radio.name = radioName;
        radio.value = option.id;
        radio.checked = option.id === current.memoryStart;
        const text = el('span', 'project-option-text');
        text.append(el('span', 'project-option-label', option.label), el('span', 'project-option-desc', option.description));
        row.append(radio, text);
        startList.appendChild(row);
      });
      body.appendChild(startList);

      const documents = checkboxRow(
        'Compartmentalized documents',
        'Documents made here stay here, and the AI in this project only sees this project’s documents.',
        current.documentsContained,
      );
      body.appendChild(documents.row);

      function sync() {
        startList.hidden = !memory.box.checked;
      }
      memory.box.addEventListener('change', sync);
      sync();

      const cancel = el('button', 'confirm-btn confirm-btn-secondary', 'Cancel');
      const ok = el('button', 'confirm-btn confirm-btn-primary', confirmText);
      cancel.addEventListener('click', () => close(null));
      ok.addEventListener('click', () => {
        const finalName = nameInput.value.trim();
        if (!finalName) { nameInput.focus(); return; }
        if (finalName !== name && knownProjectNames().includes(finalName)) {
          uiModule.showError(`A project called "${finalName}" already exists`);
          nameInput.focus();
          return;
        }
        const picked = startList.querySelector('input:checked');
        close({
          name: finalName,
          settings: {
            memoryContained: memory.box.checked,
            memoryStart: picked ? picked.value : 'fresh',
            documentsContained: documents.box.checked,
          },
        });
      });
      nameInput.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); ok.click(); } });
      footer.append(cancel, ok);
      nameInput.focus();
    },
  });
}

/** Create a project. Resolves to its name, or null. */
export async function createProject({ suggestedName = '' } = {}) {
  const choice = await chooseProjectSettings({ title: 'New project', name: suggestedName, confirmText: 'Create' });
  if (!choice) return null;
  try {
    await saveProjectSettings(choice.name, choice.settings);
  } catch (err) {
    uiModule.showError('Could not create the project: ' + err.message);
    return null;
  }
  await refreshProjects();
  return choice.name;
}

/** The gear: change a project's name and settings. Resolves to the
 * project's (possibly new) name, or false when cancelled or failed. */
export async function editProject(project) {
  const choice = await chooseProjectSettings({ title: 'Project settings', name: project.name, project });
  if (!choice) return false;
  try {
    let name = project.name;
    if (choice.name !== name) {
      await renameProject(name, choice.name);
      name = choice.name;
      if (_sessions) await _sessions.loadSessions();
    }
    const saved = await saveProjectSettings(name, choice.settings);
    const filed = (saved.memories_filed || 0) + (saved.documents_filed || 0);
    uiModule.showToast(filed ? `${name} saved — kept ${filed} existing item${filed === 1 ? '' : 's'} in the project` : `${name} saved`);
  } catch (err) {
    uiModule.showError('Could not save: ' + err.message);
    return false;
  }
  await refreshProjects();
  document.dispatchEvent(new CustomEvent('odysseus:projects-changed'));
  return choice.name;
}

/**
 * Before moving a chat, ask what happens to its memories and documents when
 * the move changes who can see them. Resolves to 'move', 'keep', '' (nothing
 * to ask) or null (cancelled).
 */
export async function chooseMemoryMove(sessionId, toProject) {
  let impact = null;
  try {
    const qs = new URLSearchParams({ session_id: sessionId, to: toProject || '' });
    const res = await fetch(`${API_BASE}/api/folders/move-impact?${qs}`, { credentials: 'same-origin' });
    if (res.ok) impact = await res.json();
  } catch (_) { /* fall through: move without asking */ }
  const memories = (impact && impact.memories) || 0;
  const documents = (impact && impact.documents) || 0;
  if (!memories && !documents) return '';
  const from = impact.from ? `"${impact.from}"` : 'Main';
  const to = impact.to ? `"${impact.to}"` : 'Main';
  const items = [
    memories ? `${memories} ${memories === 1 ? 'memory' : 'memories'}` : '',
    documents ? `${documents} ${documents === 1 ? 'document' : 'documents'}` : '',
  ].filter(Boolean).join(' and ');
  const result = await uiModule.styledConfirm(
    `This chat has ${items}, currently kept in ${from}. Move them with the chat to ${to}, or keep them where they are?`,
    { title: 'Move chat', confirmText: 'Move them too', alternateText: 'Keep them where they are', cancelText: 'Cancel' },
  );
  if (result === 'alternate') return 'keep';
  return result ? 'move' : null;
}

// ── Projects window: every project (Manage), and one project's page. ──

function _when(value) {
  if (!value) return '';
  const t = typeof value === 'number' ? value * (value < 1e12 ? 1000 : 1) : Date.parse(value.endsWith('Z') || value.includes('+') ? value : value + 'Z');
  if (!t || Number.isNaN(t)) return '';
  const diff = Date.now() - t;
  const h = diff / 3.6e6;
  if (h < 1) return 'just now';
  if (h < 24) return `${Math.floor(h)} hour${Math.floor(h) === 1 ? '' : 's'} ago`;
  return new Date(t).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

let _window = null;

function _closeWindow() {
  if (!_window) return;
  document.removeEventListener('keydown', _window.onKey, true);
  _window.overlay.remove();
  _window = null;
}

function _ensureWindow() {
  if (_window) return _window;
  const overlay = el('div', 'modal projects-window-overlay');
  const box = el('div', 'modal-content projects-window');
  box.setAttribute('role', 'dialog');
  box.setAttribute('aria-modal', 'true');
  box.setAttribute('aria-label', 'Projects');
  const close = el('button', 'close-btn projects-window-close', '✖');
  close.type = 'button';
  close.setAttribute('aria-label', 'Close projects');
  close.addEventListener('click', _closeWindow);
  const body = el('div', 'projects-window-body');
  box.append(close, body);
  overlay.appendChild(box);
  overlay.addEventListener('click', e => { if (e.target === overlay) _closeWindow(); });
  const onKey = e => {
    if (e.key !== 'Escape' || document.querySelector('.project-dialog-overlay')) return;
    e.preventDefault(); e.stopPropagation(); _closeWindow();
  };
  document.addEventListener('keydown', onKey, true);
  document.body.appendChild(overlay);
  _window = { overlay, body, onKey };
  return _window;
}

/** Manage: every project, with a way to open each one's page. */
export async function openProjectsWindow() {
  const win = _ensureWindow();
  await refreshProjects();
  const body = win.body;
  body.textContent = '';
  const head = el('div', 'projects-window-head');
  head.appendChild(el('h2', 'projects-window-title', 'Projects'));
  const add = el('button', 'confirm-btn confirm-btn-primary', 'New project');
  add.type = 'button';
  add.addEventListener('click', async () => {
    const name = await createProject();
    if (name) openProjectHome(name);
  });
  head.appendChild(add);
  body.appendChild(head);
  if (!_projects.length) {
    body.appendChild(el('p', 'projects-window-empty', 'No projects yet. A project groups chats and can keep its own memories and documents.'));
    return;
  }
  const list = el('div', 'projects-window-list');
  _projects.forEach(project => {
    const row = el('button', 'projects-window-row');
    row.type = 'button';
    const info = el('span', 'projects-window-row-info');
    info.appendChild(el('span', 'projects-window-row-name', project.name));
    if (project.description) info.appendChild(el('span', 'projects-window-row-desc', project.description));
    const chats = `${project.chats} ${project.chats === 1 ? 'chat' : 'chats'}`;
    info.appendChild(el('span', 'projects-window-row-meta', `${chats} · ${describeSettings(project)}`));
    row.appendChild(info);
    row.addEventListener('click', () => openProjectHome(project.name));
    list.appendChild(row);
  });
  body.appendChild(list);
}

/** A project's page: its chats, its memories and its files. */
export async function openProjectHome(name) {
  const win = _ensureWindow();
  const body = win.body;
  let data;
  try {
    const res = await fetch(`${API_BASE}/api/folders/${encodeURIComponent(name)}/home`, { credentials: 'same-origin' });
    if (!res.ok) throw new Error(await res.text());
    data = await res.json();
  } catch (err) {
    uiModule.showError('Could not open the project: ' + err.message);
    return;
  }
  const project = _projects.find(p => p.name === name) || { name, memory: data.memory, documents_private: data.documents_private };
  body.textContent = '';

  const back = el('button', 'projects-window-back', '← All projects');
  back.type = 'button';
  back.addEventListener('click', openProjectsWindow);
  body.appendChild(back);

  const page = el('div', 'project-home');
  const main = el('div', 'project-home-main');
  const side = el('div', 'project-home-side');
  page.append(main, side);
  body.appendChild(page);

  main.appendChild(el('h2', 'project-home-title', data.name));
  const desc = el('input', 'project-home-desc');
  desc.type = 'text';
  desc.value = data.description || '';
  desc.placeholder = 'Add a description';
  desc.setAttribute('aria-label', 'Project description');
  const saveDesc = async () => {
    const value = desc.value.trim();
    if (value === (data.description || '')) return;
    try {
      const res = await fetch(`${API_BASE}/api/folders/${encodeURIComponent(name)}/settings`, {
        method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...data.memory, documents_private: data.documents_private, description: value }),
      });
      if (!res.ok) throw new Error(await res.text());
      data.description = value;
      refreshProjects();
    } catch (err) {
      uiModule.showError('Could not save the description: ' + err.message);
    }
  };
  desc.addEventListener('blur', saveDesc);
  desc.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); desc.blur(); } });
  main.appendChild(desc);

  const composer = el('div', 'project-home-composer');
  const input = el('textarea', 'project-home-input');
  input.rows = 2;
  input.placeholder = `New chat in ${data.name}`;
  input.setAttribute('aria-label', `New chat in ${data.name}`);
  const start = el('button', 'confirm-btn confirm-btn-primary project-home-start', 'Start chat');
  start.type = 'button';
  const startChat = () => {
    const text = input.value.trim();
    if (!_sessions || !_sessions.setNextChatProject) return;
    _sessions.setNextChatProject(name);
    _closeWindow();
    document.getElementById('sidebar-new-chat-btn')?.click();
    if (text) {
      setTimeout(() => {
        const message = document.getElementById('message');
        if (!message) return;
        message.value = text;
        message.dispatchEvent(new Event('input', { bubbles: true }));
        document.getElementById('chat-form')?.requestSubmit();
      }, 150);
    }
  };
  start.addEventListener('click', startChat);
  input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); startChat(); } });
  composer.append(input, start);
  main.appendChild(composer);

  main.appendChild(el('div', 'project-home-heading', 'Recents'));
  const recents = el('div', 'project-home-list');
  if (!data.chats.length) recents.appendChild(el('div', 'project-home-empty', 'No chats yet.'));
  data.chats.forEach(chat => {
    const row = el('button', 'project-home-row');
    row.type = 'button';
    row.append(el('span', 'project-home-row-name', chat.name), el('span', 'project-home-row-when', _when(chat.last_active)));
    row.addEventListener('click', () => {
      _closeWindow();
      window.sessionModule?.selectSession?.(chat.id);
    });
    recents.appendChild(row);
  });
  main.appendChild(recents);

  // Side panel: settings, memory and files.
  const settingsRow = el('div', 'project-home-side-row');
  settingsRow.append(el('span', 'project-home-side-label', 'Settings'));
  const settingsBtn = el('button', 'project-home-side-action', 'Edit');
  settingsBtn.type = 'button';
  settingsBtn.addEventListener('click', async () => {
    const saved = await editProject(project);
    if (saved) openProjectHome(saved);
  });
  settingsRow.appendChild(settingsBtn);
  side.appendChild(settingsRow);
  side.appendChild(el('div', 'project-home-side-note', describeSettings(project)));

  function panel(label, count, items, renderItem, emptyText) {
    const wrap = el('div', 'project-home-panel');
    const row = el('div', 'project-home-side-row');
    const title = el('span', 'project-home-side-label', label);
    title.appendChild(el('span', 'project-home-side-count', ` ${count}`));
    const toggle = el('button', 'project-home-side-action', 'View');
    toggle.type = 'button';
    const listEl = el('div', 'project-home-side-list');
    listEl.hidden = true;
    if (!items.length) listEl.appendChild(el('div', 'project-home-empty', emptyText));
    items.forEach(item => listEl.appendChild(renderItem(item)));
    toggle.addEventListener('click', () => {
      listEl.hidden = !listEl.hidden;
      toggle.textContent = listEl.hidden ? 'View' : 'Hide';
    });
    row.append(title, toggle);
    wrap.append(row, listEl);
    side.appendChild(wrap);
  }

  panel('Memory', data.memories.length, data.memories, memory => {
    const item = el('div', 'project-home-memory');
    item.appendChild(el('span', 'project-home-memory-text', memory.text));
    const meta = [memory.private ? 'kept in this project' : 'shared with Main', _when(memory.timestamp)].filter(Boolean).join(' · ');
    item.appendChild(el('span', 'project-home-memory-meta', meta));
    return item;
  }, 'Nothing remembered from this project yet.');

  panel('Files', data.documents.length, data.documents, doc => {
    const item = el('button', 'project-home-file');
    item.type = 'button';
    item.append(el('span', 'project-home-file-name', doc.title), el('span', 'project-home-file-when', _when(doc.updated_at)));
    item.addEventListener('click', () => {
      _closeWindow();
      window.documentModule?.loadDocument?.(doc.id);
    });
    return item;
  }, 'No documents in this project yet.');

  side.appendChild(el('div', 'project-home-side-note project-home-privacy',
    data.documents_private || data.memory.share === false ? 'Compartmentalized' : 'Shares with Main'));
  input.focus();
}

export function init(sessionApi) {
  _sessions = sessionApi || null;
  if (_sessions) {
    _sessions.setProjectGroupSource({
      projects: () => _projects,
      onSettings: project => editProject(project),
      onOpen: project => openProjectHome(project.name),
      onNew: () => createProject(),
    });
  }
  refreshProjects();
  document.getElementById('projects-manage-btn')?.addEventListener('click', e => {
    e.stopPropagation();
    openProjectsWindow();
  });
}

export default {
  MEMORY_START_OPTIONS, settingsFor, describeSettings, knownProjectNames, refreshProjects,
  chooseProjectSettings, createProject, editProject, chooseMemoryMove,
  openProjectsWindow, openProjectHome, init,
};
