// Projects (chat folders) and their memory settings.
// Server rules: src/folder_memory.py. Data still lives in a chat's `folder`
// field; "project" is the name shown to people.
import uiModule from './ui.js?v=20260916largetoolscroll1';

const API_BASE = window.location.origin;

// The four memory modes offered when a project is created or edited.
export const PROJECT_MEMORY_MODES = [
  {
    id: 'shared', receive: 'all', share: true,
    label: 'Shared',
    description: 'Uses all your memories and adds to them, like chats outside a project.',
  },
  {
    id: 'fresh', receive: 'none', share: false,
    label: 'Contained, fresh start',
    description: 'Starts with no memories. Remembers only what happens in this project, and keeps it here.',
  },
  {
    id: 'frozen', receive: 'snapshot', share: false,
    label: 'Start from current memories, then contained',
    description: "Knows what Odysseus remembers today, but nothing you share later. What happens here stays here.",
  },
  {
    id: 'flowing', receive: 'all', share: false,
    label: 'Start from current memories, keep receiving',
    description: 'Keeps getting your new memories from outside. What happens here stays here.',
  },
];

export function modeFor(policy) {
  const p = policy || {};
  return PROJECT_MEMORY_MODES.find(m => m.receive === (p.receive || 'all') && m.share === (p.share !== false))
    || PROJECT_MEMORY_MODES[0];
}

let _projects = [];

export function knownProjectNames() {
  return _projects.map(p => p.name);
}

export async function refreshProjects() {
  try {
    const res = await fetch(`${API_BASE}/api/folders`, { credentials: 'same-origin' });
    if (!res.ok) return _projects;
    const data = await res.json();
    _projects = Array.isArray(data.folders) ? data.folders : [];
  } catch (_) { /* keep the last known list */ }
  return _projects;
}

async function saveProjectMemory(name, mode) {
  const res = await fetch(`${API_BASE}/api/folders/${encodeURIComponent(name)}/memory`, {
    method: 'PUT',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ receive: mode.receive, share: mode.share }),
  });
  if (!res.ok) throw new Error(await res.text());
  await refreshProjects();
  document.dispatchEvent(new CustomEvent('odysseus:projects-changed'));
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

// A modal in the same shape as styledConfirm. `build(body, close)` fills it.
function openDialog({ title, build, wide = false }) {
  return new Promise(resolve => {
    const overlay = el('div', 'modal project-dialog-overlay');
    const box = el('div', 'modal-content styled-confirm-box project-dialog' + (wide ? ' project-dialog-wide' : ''));
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

/**
 * Ask for a project's name (when `askName`) and memory mode.
 * Resolves to { name, mode } or null when cancelled.
 */
export function chooseProjectMemory({ title, name = '', askName = false, policy = null, confirmText = 'Save' } = {}) {
  return openDialog({
    title,
    build(body, footer, close) {
      let nameInput = null;
      if (askName) {
        nameInput = el('input', 'settings-input project-name-input');
        nameInput.type = 'text';
        nameInput.placeholder = 'e.g. Homework, Toronto Inheritance, Taxes';
        nameInput.value = name;
        nameInput.setAttribute('aria-label', 'Project name');
        body.appendChild(nameInput);
      }
      body.appendChild(el('p', 'project-mode-intro', 'How should this project use memory?'));
      let selected = modeFor(policy);
      const list = el('div', 'project-mode-list');
      list.setAttribute('role', 'radiogroup');
      const rows = PROJECT_MEMORY_MODES.map(mode => {
        const row = el('button', 'ask-user-option project-mode-option');
        row.type = 'button';
        row.setAttribute('role', 'radio');
        row.append(el('span', 'ask-user-option-label', mode.label), el('span', 'ask-user-option-desc', mode.description));
        row.addEventListener('click', () => { selected = mode; sync(); });
        list.appendChild(row);
        return [row, mode];
      });
      function sync() {
        rows.forEach(([row, mode]) => {
          const on = mode.id === selected.id;
          row.classList.toggle('selected', on);
          row.setAttribute('aria-checked', on ? 'true' : 'false');
        });
      }
      sync();
      body.appendChild(list);
      const cancel = el('button', 'confirm-btn confirm-btn-secondary', 'Cancel');
      const ok = el('button', 'confirm-btn confirm-btn-primary', confirmText);
      cancel.addEventListener('click', () => close(null));
      ok.addEventListener('click', () => {
        const finalName = askName ? nameInput.value.trim() : name;
        if (!finalName) { nameInput && nameInput.focus(); return; }
        close({ name: finalName, mode: selected });
      });
      footer.append(cancel, ok);
      (nameInput || ok).focus();
    },
  });
}

/** Create a project with its memory mode. Resolves to the name, or null. */
export async function createProject({ suggestedName = '' } = {}) {
  const choice = await chooseProjectMemory({ title: 'New project', name: suggestedName, askName: true, confirmText: 'Create' });
  if (!choice) return null;
  try {
    await saveProjectMemory(choice.name, choice.mode);
  } catch (err) {
    uiModule.showError('Could not create the project: ' + err.message);
    return null;
  }
  return choice.name;
}

export async function editProjectMemory(project) {
  const choice = await chooseProjectMemory({
    title: `Memory for ${project.name}`, name: project.name, policy: project.memory,
  });
  if (!choice) return false;
  try {
    await saveProjectMemory(project.name, choice.mode);
    uiModule.showToast(`${project.name}: ${choice.mode.label}`);
    return true;
  } catch (err) {
    uiModule.showError('Could not save: ' + err.message);
    return false;
  }
}

/**
 * Before moving a chat, ask what happens to its memories when the move
 * changes who can see them. Resolves to 'move', 'keep', '' (nothing to ask)
 * or null (cancelled).
 */
export async function chooseMemoryMove(sessionId, toProject) {
  let impact = null;
  try {
    const qs = new URLSearchParams({ session_id: sessionId, to: toProject || '' });
    const res = await fetch(`${API_BASE}/api/folders/move-impact?${qs}`, { credentials: 'same-origin' });
    if (res.ok) impact = await res.json();
  } catch (_) { /* fall through: move without asking */ }
  if (!impact || !impact.memories) return '';
  const from = impact.from ? `"${impact.from}"` : 'outside any project';
  const to = impact.to ? `"${impact.to}"` : 'outside any project';
  const n = impact.memories;
  const result = await uiModule.styledConfirm(
    `This chat has ${n} ${n === 1 ? 'memory' : 'memories'}, currently filed ${from}. ` +
    `Move ${n === 1 ? 'it' : 'them'} with the chat to ${to}, or keep ${n === 1 ? 'it' : 'them'} where ${n === 1 ? 'it is' : 'they are'}?`,
    { title: 'Move chat', confirmText: 'Move memories too', alternateText: 'Keep them where they are', cancelText: 'Cancel' },
  );
  if (result === 'alternate') return 'keep';
  return result ? 'move' : null;
}

/** The Projects manager: list projects with their memory mode. */
export async function openProjectsManager() {
  await refreshProjects();
  return openDialog({
    title: 'Projects',
    wide: true,
    build(body, footer, close) {
      function render() {
        body.textContent = '';
        if (!_projects.length) {
          body.appendChild(el('p', 'project-empty', 'No projects yet. A project groups chats and decides how they use memory.'));
        }
        const list = el('div', 'project-list');
        _projects.forEach(project => {
          const row = el('div', 'project-row');
          const info = el('div', 'project-row-info');
          info.appendChild(el('div', 'project-row-name', project.name));
          const chats = `${project.chats} ${project.chats === 1 ? 'chat' : 'chats'}`;
          const priv = project.private_memories
            ? ` · ${project.private_memories} private ${project.private_memories === 1 ? 'memory' : 'memories'}` : '';
          info.appendChild(el('div', 'project-row-meta', `${chats} · ${modeFor(project.memory).label}${priv}`));
          const edit = el('button', 'confirm-btn confirm-btn-secondary project-row-edit', 'Memory…');
          edit.addEventListener('click', async () => {
            if (await editProjectMemory(project)) render();
          });
          row.append(info, edit);
          list.appendChild(row);
        });
        body.appendChild(list);
      }
      render();
      const done = el('button', 'confirm-btn confirm-btn-secondary', 'Close');
      const add = el('button', 'confirm-btn confirm-btn-primary', 'New project');
      done.addEventListener('click', () => close(null));
      add.addEventListener('click', async () => { if (await createProject()) render(); });
      footer.append(done, add);
      add.focus();
    },
  });
}

export function init() {
  refreshProjects();
  document.getElementById('projects-section-title')?.addEventListener('click', () => openProjectsManager());
  document.getElementById('projects-new-btn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    createProject();
  });
}

export default {
  PROJECT_MEMORY_MODES, modeFor, knownProjectNames, refreshProjects, chooseProjectMemory,
  createProject, editProjectMemory, chooseMemoryMove, openProjectsManager, init,
};
