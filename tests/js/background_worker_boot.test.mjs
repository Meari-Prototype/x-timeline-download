import assert from 'node:assert/strict';
import test from 'node:test';

test('background service worker module boots with Chrome API stubs', async () => {
  const listeners = [];
  globalThis.chrome = {
    debugger: {
      attach() {},
      detach() {},
      sendCommand() {},
      onEvent: { addListener(listener) { listeners.push(listener); } },
      onDetach: { addListener(listener) { listeners.push(listener); } },
    },
    runtime: {
      lastError: null,
      connectNative() {
        return {
          postMessage() {},
          onMessage: { addListener(listener) { listeners.push(listener); } },
          onDisconnect: { addListener(listener) { listeners.push(listener); } },
        };
      },
      onMessage: { addListener(listener) { listeners.push(listener); } },
    },
    tabs: {
      query() {},
      onRemoved: { addListener(listener) { listeners.push(listener); } },
      onUpdated: { addListener(listener) { listeners.push(listener); } },
    },
  };

  await import(`../../extension/background.mjs?boot=${Date.now()}`);

  assert.equal(listeners.length >= 5, true);
});
