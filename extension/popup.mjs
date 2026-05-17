const statusEl = document.getElementById('status');
const rawJsonEl = document.getElementById('rawJson');
const tweetsEl = document.getElementById('tweets');
const imagesEl = document.getElementById('images');
const errorsEl = document.getElementById('errors');
const sessionIdEl = document.getElementById('sessionId');
const extensionIdEl = document.getElementById('extensionId');
const tabUrlEl = document.getElementById('tabUrl');
const lastErrorEl = document.getElementById('lastError');
const startButton = document.getElementById('startButton');
const stopButton = document.getElementById('stopButton');
const refreshButton = document.getElementById('refreshButton');
const sessionsListEl = document.getElementById('sessionsList');

let currentState = { status: 'idle', sessionId: null };

extensionIdEl.textContent = chrome.runtime.id ?? '未知';

startButton.addEventListener('click', async () => {
  await runAction({ type: 'start_current_tab' });
});

stopButton.addEventListener('click', async () => {
  await runAction({ type: 'stop_current_tab' });
});

refreshButton.addEventListener('click', async () => {
  await refreshAll();
});

await refreshAll();

async function refreshAll() {
  setBusy(true);
  try {
    const response = await sendMessage({ type: 'get_state' });
    renderState(response);
    await refreshSessions();
  } catch (error) {
    renderState({ ok: false, error: String(error?.message ?? error), state: { status: 'idle' } });
    renderSessions([]);
  } finally {
    setBusy(false);
  }
}

async function runAction(message) {
  setBusy(true);
  try {
    const response = await sendMessage(message);
    renderState(response);
    await refreshSessions();
  } catch (error) {
    renderState({ ok: false, error: String(error?.message ?? error), state: { status: 'idle' } });
  } finally {
    setBusy(false);
  }
}

async function refreshSessions() {
  const response = await sendMessage({ type: 'list_sessions' });
  if (!response?.ok) {
    renderState({ ok: false, error: response?.error ?? '无法读取抓取记录', state: currentState });
    return;
  }
  renderSessions(response.sessions ?? []);
}

async function sendMessage(message) {
  return chrome.runtime.sendMessage(message);
}

function renderState(response) {
  const state = response?.state ?? {};
  const counters = state.counters ?? {};
  const listening = state.status === 'listening';
  currentState = state;

  statusEl.textContent = listening ? '监听中' : '未监听';
  statusEl.classList.toggle('listening', listening);
  rawJsonEl.textContent = String(counters.rawJson ?? 0);
  tweetsEl.textContent = String(counters.tweets ?? 0);
  imagesEl.textContent = String(counters.images ?? 0);
  errorsEl.textContent = String(counters.errors ?? 0);
  sessionIdEl.textContent = state.sessionId ?? '无';
  tabUrlEl.textContent = response?.tab?.url ?? '无当前 tab';

  const error = response?.error ?? state.lastError;
  lastErrorEl.hidden = !error;
  lastErrorEl.textContent = error ? String(error) : '';

  startButton.disabled = listening;
  stopButton.disabled = !listening;
}

function renderSessions(sessions) {
  sessionsListEl.replaceChildren();

  if (sessions.length === 0) {
    const empty = document.createElement('p');
    empty.className = 'empty';
    empty.textContent = '暂无抓取记录';
    sessionsListEl.append(empty);
    return;
  }

  for (const session of sessions) {
    const item = document.createElement('article');
    item.className = 'session-item';

    const titleRow = document.createElement('div');
    titleRow.className = 'session-title-row';

    const title = document.createElement('h3');
    title.textContent = session.id ?? 'unknown-session';

    const badge = document.createElement('span');
    badge.className = `session-badge ${session.status === 'active' ? 'active' : ''}`;
    badge.textContent = session.status === 'active' ? '进行中' : '已结束';

    titleRow.append(title, badge);

    const meta = document.createElement('p');
    meta.className = 'session-meta';
    meta.textContent = formatSessionMeta(session);

    const url = document.createElement('p');
    url.className = 'session-url';
    url.textContent = session.tabUrl || '无 URL';

    const footer = document.createElement('div');
    footer.className = 'session-footer';

    const path = document.createElement('p');
    path.className = 'session-path';
    path.textContent = session.path || '';

    const actions = document.createElement('div');
    actions.className = 'session-actions';

    const generateButton = document.createElement('button');
    generateButton.className = 'secondary-button';
    generateButton.type = 'button';
    generateButton.textContent = '手动生成';
    generateButton.addEventListener('click', async () => {
      await generateSessionExport(session.id);
    });

    const pureButton = document.createElement('button');
    pureButton.className = 'secondary-button';
    pureButton.type = 'button';
    pureButton.textContent = '洗语料';
    pureButton.addEventListener('click', async () => {
      await generatePureExport(session.id);
    });

    const openButton = document.createElement('button');
    openButton.className = 'secondary-button';
    openButton.type = 'button';
    openButton.textContent = '打开目录';
    openButton.addEventListener('click', async () => {
      await openSessionDirectory(session.id);
    });

    const deleteButton = document.createElement('button');
    deleteButton.className = 'danger-button';
    deleteButton.type = 'button';
    deleteButton.textContent = '删除';
    deleteButton.disabled = session.status === 'active';
    deleteButton.addEventListener('click', async () => {
      await deleteSession(session.id);
    });

    actions.append(generateButton, pureButton, openButton, deleteButton);
    footer.append(path, actions);
    item.append(titleRow, meta, url, footer);
    sessionsListEl.append(item);
  }
}

async function generateSessionExport(sessionId) {
  if (!sessionId) return;

  setBusy(true);
  try {
    const response = await sendMessage({ type: 'generate_session_export', sessionId });
    if (!response?.ok) throw new Error(response?.error ?? '手动生成失败');
    renderState(response);
    await refreshSessions();
  } catch (error) {
    renderState({ ok: false, error: String(error?.message ?? error), state: currentState });
  } finally {
    setBusy(false);
  }
}

async function generatePureExport(sessionId) {
  if (!sessionId) return;

  setBusy(true);
  try {
    const response = await sendMessage({ type: 'generate_pure_export', sessionId });
    if (!response?.ok) throw new Error(response?.error ?? '洗语料失败');
    renderState(response);
    await refreshSessions();
  } catch (error) {
    renderState({ ok: false, error: String(error?.message ?? error), state: currentState });
  } finally {
    setBusy(false);
  }
}

async function openSessionDirectory(sessionId) {
  if (!sessionId) return;

  setBusy(true);
  try {
    const response = await sendMessage({ type: 'open_session_directory', sessionId });
    if (!response?.ok) throw new Error(response?.error ?? '打开目录失败');
    renderState(response);
  } catch (error) {
    renderState({ ok: false, error: String(error?.message ?? error), state: currentState });
  } finally {
    setBusy(false);
  }
}

async function deleteSession(sessionId) {
  if (!sessionId) return;
  if (!confirm(`删除这次抓取记录？\n${sessionId}`)) return;

  setBusy(true);
  try {
    const response = await sendMessage({ type: 'delete_session', sessionId });
    if (!response?.ok) throw new Error(response?.error ?? '删除失败');
    renderState(response);
    await refreshSessions();
  } catch (error) {
    renderState({ ok: false, error: String(error?.message ?? error), state: currentState });
  } finally {
    setBusy(false);
  }
}

function formatSessionMeta(session) {
  const counters = session.counters ?? {};
  const started = formatDate(session.started_at);
  const ended = session.ended_at ? ` / 结束 ${formatDate(session.ended_at)}` : '';
  return [
    `开始 ${started}${ended}`,
    `JSON ${counters.rawJson ?? 0}`,
    `帖子 ${counters.tweets ?? 0}`,
    `图片 ${counters.images ?? 0}`,
    `错误 ${counters.errors ?? 0}`,
  ].join(' · ');
}

function formatDate(value) {
  if (!value) return '未知';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('zh-CN', { hour12: false });
}

function setBusy(isBusy) {
  const listening = currentState.status === 'listening';
  startButton.disabled = isBusy || listening;
  stopButton.disabled = isBusy || !listening;
  refreshButton.disabled = isBusy;
}
