import { BackgroundCaptureCore } from './lib/background_core.mjs';

const HOST_NAME = 'com.master.x_tweet_fetcher';

class NativeHostClient {
  constructor(hostName) {
    this.hostName = hostName;
    this.port = null;
    this.queue = [];
    this.inFlight = null;
  }

  send(message) {
    return new Promise((resolve, reject) => {
      this.queue.push({ message, resolve, reject });
      this.pump();
    });
  }

  pump() {
    if (this.inFlight || this.queue.length === 0) return;
    this.ensurePort();
    this.inFlight = this.queue.shift();
    try {
      this.port.postMessage(this.inFlight.message);
    } catch (error) {
      const current = this.inFlight;
      this.inFlight = null;
      this.port = null;
      current.reject(error);
      this.pump();
    }
  }

  ensurePort() {
    if (this.port) return;
    this.port = chrome.runtime.connectNative(this.hostName);
    this.port.onMessage.addListener((response) => {
      const current = this.inFlight;
      this.inFlight = null;
      current?.resolve(response);
      this.pump();
    });
    this.port.onDisconnect.addListener(() => {
      const error = new Error(chrome.runtime.lastError?.message ?? 'Native host disconnected');
      this.port = null;
      if (this.inFlight) {
        this.inFlight.reject(error);
        this.inFlight = null;
      }
      while (this.queue.length > 0) {
        this.queue.shift().reject(error);
      }
    });
  }
}

const nativeHost = new NativeHostClient(HOST_NAME);

const core = new BackgroundCaptureCore({
  attach: (tabId) => callChrome((done) => chrome.debugger.attach({ tabId }, '1.3', done)),
  detach: (tabId) => callChrome((done) => chrome.debugger.detach({ tabId }, done)),
  sendCommand: (tabId, method, params = undefined) =>
    callChrome((done) => chrome.debugger.sendCommand({ tabId }, method, params ?? {}, done)),
  sendNativeMessage: (message) => nativeHost.send(message),
});

chrome.debugger.onEvent.addListener((source, method, params) => {
  core.handleCdpEvent(source, method, params).catch((error) => {
    console.warn('capture event failed', error);
  });
});

chrome.debugger.onDetach.addListener((source) => {
  if (source?.tabId) core.forget(source.tabId);
});

chrome.tabs.onRemoved.addListener((tabId) => {
  core.forget(tabId);
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'loading' && tab.url && !isXUrl(tab.url)) {
    core.stop(tabId).catch(() => core.forget(tabId));
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message).then(sendResponse, (error) => {
    sendResponse({ ok: false, error: String(error?.message ?? error) });
  });
  return true;
});

async function handleMessage(message) {
  const tab = await getActiveTab();
  const tabId = tab?.id;

  if (message?.type === 'get_state') {
    return { ok: true, tab: summarizeTab(tab), state: core.getState(tabId) };
  }

  if (message?.type === 'start_current_tab') {
    const result = await core.start(tab);
    return { ...result, tab: summarizeTab(tab), state: core.getState(tabId) };
  }

  if (message?.type === 'stop_current_tab') {
    const result = await core.stop(tabId);
    return { ...result, tab: summarizeTab(tab), state: core.getState(tabId) };
  }

  if (message?.type === 'list_sessions') {
    const result = await core.listSessions();
    return { ...result, tab: summarizeTab(tab), state: core.getState(tabId) };
  }

  if (message?.type === 'generate_session_export') {
    const result = await core.generateSessionExport(message.sessionId);
    return { ...result, tab: summarizeTab(tab), state: core.getState(tabId) };
  }

  if (message?.type === 'generate_pure_export') {
    const result = await core.generatePureExport(message.sessionId);
    return { ...result, tab: summarizeTab(tab), state: core.getState(tabId) };
  }

  if (message?.type === 'open_session_directory') {
    const result = await core.openSessionDirectory(message.sessionId);
    return { ...result, tab: summarizeTab(tab), state: core.getState(tabId) };
  }

  if (message?.type === 'delete_session') {
    const result = await core.deleteSession(message.sessionId);
    return { ...result, tab: summarizeTab(tab), state: core.getState(tabId) };
  }

  return { ok: false, error: `Unknown message type: ${message?.type}` };
}

async function getActiveTab() {
  const tabs = await callChrome((done) =>
    chrome.tabs.query({ active: true, currentWindow: true }, done),
  );
  return tabs?.[0] ?? null;
}

function summarizeTab(tab) {
  if (!tab) return null;
  return { id: tab.id, url: tab.url, title: tab.title };
}

function isXUrl(url) {
  try {
    const host = new URL(url).hostname;
    return host === 'x.com' || host === 'twitter.com';
  } catch {
    return false;
  }
}

function callChrome(invoker) {
  return new Promise((resolve, reject) => {
    invoker((result) => {
      const error = chrome.runtime.lastError;
      if (error) {
        reject(new Error(error.message));
        return;
      }
      resolve(result);
    });
  });
}
