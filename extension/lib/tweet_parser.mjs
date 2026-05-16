import { getPbsMediaIdentity } from './filters.mjs';

export function extractTweets(payload) {
  const found = new Map();
  const visited = new WeakSet();

  walk(payload, (value) => {
    const tweet = unwrapTweet(value);
    if (!tweet) return;
    const normalized = normalizeTweet(tweet);
    if (!normalized || found.has(normalized.id)) return;
    found.set(normalized.id, normalized);
  }, visited);

  return [...found.values()];
}

function walk(value, visit, visited) {
  if (!value || typeof value !== 'object') return;
  if (visited.has(value)) return;
  visited.add(value);

  visit(value);

  if (Array.isArray(value)) {
    for (const item of value) walk(item, visit, visited);
    return;
  }

  for (const item of Object.values(value)) {
    walk(item, visit, visited);
  }
}

function unwrapTweet(value) {
  if (!value || typeof value !== 'object') return null;

  if (value.__typename === 'TweetWithVisibilityResults' && value.tweet) {
    return unwrapTweet(value.tweet);
  }

  if (value.tweet_results?.result) {
    return unwrapTweet(value.tweet_results.result);
  }

  if (value.result && looksLikeTweet(value.result)) {
    return unwrapTweet(value.result);
  }

  if (looksLikeTweet(value)) return value;
  return null;
}

function looksLikeTweet(value) {
  if (typeof value?.__typename === 'string' && value.__typename !== 'Tweet') {
    return false;
  }

  return Boolean(
    value &&
      typeof value === 'object' &&
      typeof value.rest_id === 'string' &&
      value.legacy &&
      typeof value.legacy === 'object' &&
      (typeof value.legacy.full_text === 'string' ||
        typeof value.legacy.created_at === 'string' ||
        value.legacy.entities ||
        value.legacy.extended_entities),
  );
}

function normalizeTweet(tweet) {
  const id = tweet.rest_id;
  if (!id) return null;

  return {
    id,
    text: getTweetText(tweet),
    createdAt: tweet.legacy?.created_at ?? null,
    author: normalizeAuthor(tweet.core?.user_results?.result),
    mediaImages: extractPhotoMedia(tweet),
    rawTypename: tweet.__typename ?? null,
  };
}

function getTweetText(tweet) {
  const noteText = tweet.note_tweet?.note_tweet_results?.result?.text;
  if (typeof noteText === 'string') return noteText;
  return tweet.legacy?.full_text ?? '';
}

function normalizeAuthor(user) {
  if (!user || typeof user !== 'object') return null;
  return {
    id: user.rest_id ?? user.id_str ?? null,
    screenName: user.legacy?.screen_name ?? user.core?.screen_name ?? user.screen_name ?? null,
    name: user.legacy?.name ?? user.core?.name ?? user.name ?? null,
  };
}

function extractPhotoMedia(tweet) {
  const mediaItems = [
    ...(tweet.legacy?.extended_entities?.media ?? []),
    ...(tweet.legacy?.entities?.media ?? []),
  ];
  const seen = new Set();
  const images = [];

  for (const media of mediaItems) {
    if (!media || media.type !== 'photo') continue;
    const url = media.media_url_https ?? media.media_url ?? null;
    const identity = getPbsMediaIdentity(url);
    if (!url || !identity || seen.has(identity)) continue;
    seen.add(identity);
    images.push({
      url,
      identity,
      expandedUrl: media.expanded_url ?? null,
    });
  }

  return images;
}
