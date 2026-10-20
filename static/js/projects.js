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

/** The gear: change a project's name and settings. */
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
  return true;
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

export function init(sessionApi) {
  _sessions = sessionApi || null;
  if (_sessions) {
    _sessions.setProjectGroupSource({
      projects: () => _projects,
      onSettings: project => editProject(project),
      onNew: () => createProject(),
    });
  }
  refreshProjects();
}

export default {
  MEMORY_START_OPTIONS, settingsFor, describeSettings, knownProjectNames, refreshProjects,
  chooseProjectSettings, createProject, editProject, chooseMemoryMove, init,
};
