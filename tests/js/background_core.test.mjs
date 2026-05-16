import assert from 'node:assert/strict';
import test from 'node:test';

import { BackgroundCaptureCore } from '../../extension/lib/background_core.mjs';

function makeCore(responseBodies = {}) {
  const calls = [];
  let nextSession = 1;
  const core = new BackgroundCaptureCore({
    attach: async (tabId) => calls.push(['attach', tabId]),
    detach: async (tabId) => calls.push(['detach', tabId]),
    sendCommand: async (tabId, method, params) => {
      calls.push(['command', tabId, method, params ?? null]);
      if (method === 'Network.getResponseBody') {
        return responseBodies[params.requestId];
      }
      return {};
    },
    sendNativeMessage: async (message) => {
      calls.push(['native', message]);
      if (message.type === 'create_session') {
        return {
          ok: true,
          session: { id: `session-${nextSession++}`, status: 'active', counters: {} },
        };
      }
      if (message.type === 'list_sessions') {
        return { ok: true, sessions: [{ id: 'session-1', status: 'closed', counters: {} }] };
      }
      return { ok: true };
    },
  });
  return { core, calls };
}

test('starts only on X tabs and enables Network domain', async () => {
  const { core, calls } = makeCore();

  assert.equal((await core.start({ id: 1, url: 'https://example.com' })).ok, false);
  assert.equal(calls.length, 0);

  assert.equal((await core.start({ id: 2, url: 'https://x.com/home' })).ok, true);
  assert.deepEqual(calls, [
    ['native', { type: 'create_session', tabUrl: 'https://x.com/home', tabTitle: '' }],
    ['attach', 2],
    ['command', 2, 'Network.enable', null],
  ]);
  assert.equal(core.getState(2).status, 'listening');
  assert.equal(core.getState(2).sessionId, 'session-1');
});

test('stops an active session, detaches the tab, and closes the session', async () => {
  const { core, calls } = makeCore();
  await core.start({ id: 3, url: 'https://x.com/home' });

  const result = await core.stop(3);

  assert.equal(result.ok, true);
  assert.equal(core.getState(3).status, 'idle');
  assert.deepEqual(calls.slice(-2), [
    ['detach', 3],
    [
      'native',
      {
        type: 'close_session',
        sessionId: 'session-1',
        counters: { rawJson: 0, tweets: 0, images: 0, errors: 0 },
      },
    ],
  ]);
});

test('saves raw JSON, extracted tweets, and allowlists tweet body images', async () => {
  const payload = {
    data: {
      home: {
        tweet_results: {
          result: {
            __typename: 'Tweet',
            rest_id: '111',
            legacy: {
              full_text: 'hello',
              extended_entities: {
                media: [
                  {
                    type: 'photo',
                    media_url_https: 'https://pbs.twimg.com/media/Gabc123.jpg',
                  },
                ],
              },
            },
          },
        },
      },
    },
  };
  const { core, calls } = makeCore({
    json1: { body: JSON.stringify(payload), base64Encoded: false },
  });
  await core.start({ id: 4, url: 'https://x.com/home' });

  await core.handleCdpEvent(
    { tabId: 4 },
    'Network.responseReceived',
    {
      requestId: 'json1',
      type: 'XHR',
      response: {
        url: 'https://x.com/i/api/graphql/HomeTimeline',
        status: 200,
        mimeType: 'application/json',
        headers: { 'content-type': 'application/json' },
      },
    },
  );
  await core.handleCdpEvent({ tabId: 4 }, 'Network.loadingFinished', { requestId: 'json1' });

  const nativeTypes = calls.filter((call) => call[0] === 'native').map((call) => call[1].type);
  assert.deepEqual(nativeTypes, ['create_session', 'save_raw_json', 'save_tweet_json']);
  const saveMessages = calls.filter((call) => call[0] === 'native').map((call) => call[1]).slice(1);
  assert.deepEqual(saveMessages.map((message) => message.sessionId), ['session-1', 'session-1']);
  assert.deepEqual(core.getState(4).counters, {
    rawJson: 1,
    tweets: 1,
    images: 0,
    errors: 0,
  });
  assert.deepEqual(core.getAllowedImageTweetIds(4, 'pbs.twimg.com/media/Gabc123'), ['111']);
});

test('ignores empty XHR bodies without surfacing JSON parse errors', async () => {
  const { core, calls } = makeCore({
    empty1: { body: '', base64Encoded: false },
  });
  await core.start({ id: 7, url: 'https://x.com/goodhunt/with_replies' });

  await core.handleCdpEvent(
    { tabId: 7 },
    'Network.responseReceived',
    {
      requestId: 'empty1',
      type: 'XHR',
      response: {
        url: 'https://x.com/i/api/1.1/graphql/user_flow.json',
        status: 200,
        mimeType: 'application/json',
        headers: { 'content-type': 'application/json' },
      },
    },
  );
  await core.handleCdpEvent({ tabId: 7 }, 'Network.loadingFinished', { requestId: 'empty1' });

  assert.equal(calls.filter((call) => call[0] === 'native').length, 1);
  assert.deepEqual(core.getState(7).counters, {
    rawJson: 0,
    tweets: 0,
    images: 0,
    errors: 0,
  });
  assert.equal(core.getState(7).lastError, null);
});

test('saves only naturally loaded images that are allowlisted by tweet JSON', async () => {
  const { core, calls } = makeCore({
    img1: { body: 'aW1hZ2U=', base64Encoded: true },
  });
  await core.start({ id: 5, url: 'https://x.com/home' });
  core.allowImageForTweets(5, 'pbs.twimg.com/media/Gabc123', ['111']);

  await core.handleCdpEvent(
    { tabId: 5 },
    'Network.responseReceived',
    {
      requestId: 'img1',
      type: 'Image',
      response: {
        url: 'https://pbs.twimg.com/media/Gabc123?format=jpg&name=large',
        status: 200,
        mimeType: 'image/jpeg',
        headers: { 'content-type': 'image/jpeg' },
      },
    },
  );
  await core.handleCdpEvent({ tabId: 5 }, 'Network.loadingFinished', { requestId: 'img1' });

  const imageMessages = calls
    .filter((call) => call[0] === 'native')
    .map((call) => call[1])
    .filter((message) => message.type === 'save_image');
  assert.equal(imageMessages.length, 1);
  assert.equal(imageMessages[0].sessionId, 'session-1');
  assert.equal(imageMessages[0].bodyBase64, 'aW1hZ2U=');
  assert.deepEqual(imageMessages[0].tweetIds, ['111']);
  assert.equal(core.getState(5).counters.images, 1);
});

test('ignores videos and non-allowlisted images', async () => {
  const { core, calls } = makeCore({
    video1: { body: 'ignored', base64Encoded: true },
    img2: { body: 'aW1hZ2U=', base64Encoded: true },
  });
  await core.start({ id: 6, url: 'https://x.com/home' });

  await core.handleCdpEvent(
    { tabId: 6 },
    'Network.responseReceived',
    {
      requestId: 'video1',
      type: 'Media',
      response: {
        url: 'https://video.twimg.com/ext_tw_video/123/seg.m4s',
        status: 200,
        mimeType: 'video/mp4',
        headers: {},
      },
    },
  );
  await core.handleCdpEvent({ tabId: 6 }, 'Network.loadingFinished', { requestId: 'video1' });

  await core.handleCdpEvent(
    { tabId: 6 },
    'Network.responseReceived',
    {
      requestId: 'img2',
      type: 'Image',
      response: {
        url: 'https://pbs.twimg.com/media/GnotAllowed?format=jpg&name=small',
        status: 200,
        mimeType: 'image/jpeg',
        headers: {},
      },
    },
  );
  await core.handleCdpEvent({ tabId: 6 }, 'Network.loadingFinished', { requestId: 'img2' });

  assert.equal(calls.filter((call) => call[0] === 'native').length, 1);
  assert.equal(core.getState(6).requestCount, 0);
});

test('lists, generates exports, generates pure text, opens, and deletes stored sessions through the native host', async () => {
  const { core, calls } = makeCore();

  const listed = await core.listSessions();
  const generated = await core.generateSessionExport('session-1');
  const pure = await core.generatePureExport('session-1');
  const opened = await core.openSessionDirectory('session-1');
  const deleted = await core.deleteSession('session-1');

  assert.equal(listed.sessions.length, 1);
  assert.equal(generated.ok, true);
  assert.equal(pure.ok, true);
  assert.equal(opened.ok, true);
  assert.equal(deleted.ok, true);
  assert.deepEqual(calls.filter((call) => call[0] === 'native').map((call) => call[1]), [
    { type: 'list_sessions' },
    { type: 'generate_session_export', sessionId: 'session-1' },
    { type: 'generate_pure_export', sessionId: 'session-1' },
    { type: 'open_session_directory', sessionId: 'session-1' },
    { type: 'delete_session', sessionId: 'session-1' },
  ]);
});
