import { classifyResponse, getPbsMediaIdentity, isAllowedXPage, isXNetworkUrl } from './filters.mjs';
import { extractTweets } from './tweet_parser.mjs';

export class BackgroundCaptureCore {
  constructor(adapter) {
    this.adapter = adapter;
    this.sessions = new Map();
  }

  async start(tab) {
    if (!tab?.id || !isAllowedXPage(tab.url)) {
      return { ok: false, error: 'Current page is not X' };
    }

    if (this.sessions.has(tab.id)) {
      return { ok: true, status: 'listening' };
    }

    let created;
    try {
      created = await this.adapter.sendNativeMessage({
        type: 'create_session',
        tabUrl: tab.url,
        tabTitle: tab.title ?? '',
      });
    } catch (error) {
      return { ok: false, error: String(error?.message ?? error) };
    }
    if (!created?.ok || !created?.session?.id) {
      return { ok: false, error: created?.error ?? 'Native host did not create a session' };
    }

    let attached = false;
    const session = createSession(tab.id, tab.url, created.session.id);
    try {
      await this.adapter.attach(tab.id);
      attached = true;
      this.sessions.set(tab.id, session);
      await this.adapter.sendCommand(tab.id, 'Network.enable');
    } catch (error) {
      this.sessions.delete(tab.id);
      if (attached) await this.adapter.detach(tab.id).catch(() => {});
      await this.closeNativeSession(session).catch(() => {});
      return { ok: false, error: String(error?.message ?? error) };
    }

    return { ok: true, status: 'listening' };
  }

  async stop(tabId) {
    const session = this.sessions.get(tabId);
    if (!session) {
      return { ok: true, status: 'idle' };
    }
    this.sessions.delete(tabId);
    let errorText = null;
    try {
      await this.adapter.detach(tabId);
    } catch (error) {
      errorText = String(error?.message ?? error);
    }
    const closed = await this.closeNativeSession(session).catch((error) => ({
      ok: false,
      error: String(error?.message ?? error),
    }));
    if (errorText || !closed?.ok) {
      return { ok: false, status: 'idle', error: errorText ?? closed?.error };
    }
    return { ok: true, status: 'idle' };
  }

  forget(tabId) {
    const session = this.sessions.get(tabId);
    this.sessions.delete(tabId);
    if (session) this.closeNativeSession(session).catch(() => {});
  }

  getState(tabId) {
    const session = this.sessions.get(tabId);
    if (!session) {
      return {
        status: 'idle',
        counters: { rawJson: 0, tweets: 0, images: 0, errors: 0 },
        requestCount: 0,
        lastError: null,
        sessionId: null,
      };
    }
    return {
      status: 'listening',
      counters: { ...session.counters },
      requestCount: session.requests.size,
      lastError: session.lastError,
      sessionId: session.sessionId,
    };
  }

  getAllowedImageTweetIds(tabId, identity) {
    const session = this.sessions.get(tabId);
    const entry = session?.allowedImages.get(identity);
    return entry ? [...entry.tweetIds].sort() : [];
  }

  allowImageForTweets(tabId, identity, tweetIds) {
    const session = this.sessions.get(tabId);
    if (!session || !identity) return;
    const entry = session.allowedImages.get(identity) ?? { tweetIds: new Set() };
    for (const tweetId of tweetIds) entry.tweetIds.add(String(tweetId));
    session.allowedImages.set(identity, entry);
  }

  async handleCdpEvent(source, method, params) {
    const tabId = source?.tabId;
    const session = this.sessions.get(tabId);
    if (!session) return;

    if (method === 'Network.responseReceived') {
      this.handleResponseReceived(session, params);
      return;
    }

    if (method === 'Network.loadingFinished') {
      await this.handleLoadingFinished(session, params);
    }
  }

  handleResponseReceived(session, params) {
    const response = params?.response;
    if (!response?.url || !isXNetworkUrl(response.url)) return;

    const metadata = {
      requestId: params.requestId,
      url: response.url,
      status: response.status,
      mimeType: response.mimeType,
      resourceType: params.type,
      headers: response.headers ?? {},
    };
    const classification = classifyResponse(metadata);
    if (classification === 'ignore' || classification === 'video') return;
    session.requests.set(params.requestId, { ...metadata, classification });
  }

  async handleLoadingFinished(session, params) {
    const metadata = session.requests.get(params?.requestId);
    if (!metadata) return;
    session.requests.delete(params.requestId);

    try {
      if (metadata.classification === 'json') {
        await this.handleJsonBody(session, metadata);
        return;
      }

      if (metadata.classification === 'image') {
        await this.handleImageBody(session, metadata);
      }
    } catch (error) {
      await this.recordError(session, {
        stage: 'get_response_body',
        requestId: metadata.requestId,
        url: metadata.url,
        classification: metadata.classification,
        message: String(error?.message ?? error),
      });
    }
  }

  async handleJsonBody(session, metadata) {
    const body = await this.getResponseBody(session.tabId, metadata.requestId);
    const text = decodeTextBody(body.body, body.base64Encoded);
    if (!text.trim()) return;

    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch (error) {
      await this.recordError(session, {
        stage: 'json_parse',
        requestId: metadata.requestId,
        url: metadata.url,
        message: String(error?.message ?? error),
      });
      return;
    }

    const savedRaw = await this.sendNative(session, {
      type: 'save_raw_json',
      record: {
        url: metadata.url,
        status: metadata.status,
        mimeType: metadata.mimeType,
        body: parsed,
      },
    });
    if (savedRaw?.ok) session.counters.rawJson += 1;

    for (const tweet of extractTweets(parsed)) {
      const savedTweet = await this.sendNative(session, { type: 'save_tweet_json', tweet });
      if (savedTweet?.ok) session.counters.tweets += 1;
      for (const image of tweet.mediaImages) {
        this.allowImageForTweets(session.tabId, image.identity, [tweet.id]);
      }
    }
  }

  async handleImageBody(session, metadata) {
    const identity = getPbsMediaIdentity(metadata.url);
    const tweetIds = this.getAllowedImageTweetIds(session.tabId, identity);
    if (tweetIds.length === 0) return;

    const body = await this.getResponseBody(session.tabId, metadata.requestId);
    const savedImage = await this.sendNative(session, {
      type: 'save_image',
      url: metadata.url,
      mimeType: metadata.mimeType,
      bodyBase64: encodeBodyAsBase64(body.body, body.base64Encoded),
      tweetIds,
    });
    if (savedImage?.ok && !savedImage.skipped) session.counters.images += 1;
  }

  async getResponseBody(tabId, requestId) {
    return this.adapter.sendCommand(tabId, 'Network.getResponseBody', { requestId });
  }

  async sendNative(session, message) {
    const payload = session?.sessionId ? { ...message, sessionId: session.sessionId } : message;
    let result;
    try {
      result = await this.adapter.sendNativeMessage(payload);
    } catch (error) {
      const messageText = String(error?.message ?? error);
      await this.recordError(session, {
        stage: 'native',
        message: messageText,
        inputType: message.type,
      });
      return { ok: false, error: messageText };
    }
    if (!result?.ok) {
      await this.recordError(session, {
        stage: 'native',
        message: result?.error ?? 'Native host returned failure',
        inputType: message.type,
      });
    }
    return result;
  }

  async recordError(session, error) {
    session.counters.errors += 1;
    session.lastError = String(error?.message ?? error);
    await this.adapter
      .sendNativeMessage({ type: 'save_error', sessionId: session.sessionId, error })
      .catch(() => {});
  }

  async closeNativeSession(session) {
    if (!session?.sessionId) return { ok: true };
    return this.adapter.sendNativeMessage({
      type: 'close_session',
      sessionId: session.sessionId,
      counters: { ...session.counters },
    });
  }

  async listSessions() {
    return this.adapter.sendNativeMessage({ type: 'list_sessions' });
  }

  async generateSessionExport(sessionId) {
    return this.adapter.sendNativeMessage({ type: 'generate_session_export', sessionId });
  }

  async generatePureExport(sessionId) {
    return this.adapter.sendNativeMessage({ type: 'generate_pure_export', sessionId });
  }

  async openSessionDirectory(sessionId) {
    return this.adapter.sendNativeMessage({ type: 'open_session_directory', sessionId });
  }

  async deleteSession(sessionId) {
    return this.adapter.sendNativeMessage({ type: 'delete_session', sessionId });
  }
}

function createSession(tabId, url, sessionId) {
  return {
    tabId,
    url,
    sessionId,
    requests: new Map(),
    allowedImages: new Map(),
    counters: {
      rawJson: 0,
      tweets: 0,
      images: 0,
      errors: 0,
    },
    lastError: null,
  };
}

function decodeTextBody(body, base64Encoded) {
  if (!base64Encoded) return body;
  const bytes = decodeBase64Bytes(body);
  return new TextDecoder().decode(bytes);
}

function encodeBodyAsBase64(body, base64Encoded) {
  if (base64Encoded) return body;
  if (typeof btoa === 'function') return btoa(body);
  return Buffer.from(body, 'utf-8').toString('base64');
}

function decodeBase64Bytes(value) {
  if (typeof atob === 'function') {
    return Uint8Array.from(atob(value), (char) => char.charCodeAt(0));
  }
  return Uint8Array.from(Buffer.from(value, 'base64'));
}
