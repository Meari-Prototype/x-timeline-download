import assert from 'node:assert/strict';
import test from 'node:test';

import {
  classifyResponse,
  getPbsMediaIdentity,
  isAllowedXPage,
  isXNetworkUrl,
} from '../../extension/lib/filters.mjs';

test('accepts only Chrome tabs on X pages as capture targets', () => {
  assert.equal(isAllowedXPage('https://x.com/home'), true);
  assert.equal(isAllowedXPage('https://twitter.com/home'), true);
  assert.equal(isAllowedXPage('https://mobile.twitter.com/home'), false);
  assert.equal(isAllowedXPage('https://example.com/home'), false);
  assert.equal(isAllowedXPage('not a url'), false);
});

test('keeps X API and pbs media URLs but rejects unrelated domains', () => {
  assert.equal(isXNetworkUrl('https://x.com/i/api/graphql/HomeTimeline'), true);
  assert.equal(isXNetworkUrl('https://api.x.com/graphql/HomeTimeline'), true);
  assert.equal(isXNetworkUrl('https://twitter.com/i/api/graphql/HomeTimeline'), true);
  assert.equal(isXNetworkUrl('https://pbs.twimg.com/media/Gabc123?format=jpg&name=small'), true);
  assert.equal(isXNetworkUrl('https://video.twimg.com/ext_tw_video/foo.m4s'), false);
  assert.equal(isXNetworkUrl('https://example.com/media/Gabc123.jpg'), false);
});

test('classifies JSON, tweet body image, video, and irrelevant responses', () => {
  assert.equal(
    classifyResponse({
      url: 'https://x.com/i/api/graphql/HomeTimeline',
      mimeType: 'application/json',
      resourceType: 'XHR',
      headers: { 'content-type': 'application/json; charset=utf-8' },
    }),
    'json',
  );

  assert.equal(
    classifyResponse({
      url: 'https://pbs.twimg.com/media/Gabc123?format=jpg&name=large',
      mimeType: 'image/jpeg',
      resourceType: 'Image',
      headers: {},
    }),
    'image',
  );

  assert.equal(
    classifyResponse({
      url: 'https://video.twimg.com/ext_tw_video/123/pu/vid/avc1/seg.m4s',
      mimeType: 'video/mp4',
      resourceType: 'Media',
      headers: {},
    }),
    'video',
  );

  assert.equal(
    classifyResponse({
      url: 'https://abs.twimg.com/responsive-web/client-web/main.js',
      mimeType: 'application/javascript',
      resourceType: 'Script',
      headers: {},
    }),
    'ignore',
  );
});

test('normalizes pbs media URL variants to the same identity', () => {
  assert.equal(
    getPbsMediaIdentity('https://pbs.twimg.com/media/Gabc123.jpg'),
    'pbs.twimg.com/media/Gabc123',
  );
  assert.equal(
    getPbsMediaIdentity('https://pbs.twimg.com/media/Gabc123?format=jpg&name=small'),
    'pbs.twimg.com/media/Gabc123',
  );
  assert.equal(getPbsMediaIdentity('https://pbs.twimg.com/profile_images/1/avatar.jpg'), null);
  assert.equal(getPbsMediaIdentity('not a url'), null);
});
