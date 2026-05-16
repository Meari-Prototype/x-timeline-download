const X_PAGE_HOSTS = new Set(['x.com', 'twitter.com']);
const X_API_HOSTS = new Set(['x.com', 'api.x.com', 'twitter.com', 'api.twitter.com']);

export function isAllowedXPage(url) {
  const parsed = parseUrl(url);
  return Boolean(parsed && X_PAGE_HOSTS.has(parsed.hostname));
}

export function isXNetworkUrl(url) {
  const parsed = parseUrl(url);
  if (!parsed) return false;
  if (X_API_HOSTS.has(parsed.hostname)) return true;
  return parsed.hostname === 'pbs.twimg.com' && parsed.pathname.startsWith('/media/');
}

export function classifyResponse(metadata) {
  const url = metadata?.url ?? '';
  const parsed = parseUrl(url);
  if (!parsed) return 'ignore';

  const resourceType = String(metadata?.resourceType ?? '').toLowerCase();
  const mimeType = String(metadata?.mimeType ?? '').toLowerCase();
  const contentType = String(getHeader(metadata?.headers, 'content-type') ?? '').toLowerCase();
  const pathname = parsed.pathname.toLowerCase();

  if (
    resourceType === 'media' ||
    mimeType.startsWith('video/') ||
    mimeType.startsWith('audio/') ||
    contentType.startsWith('video/') ||
    contentType.startsWith('audio/') ||
    pathname.endsWith('.m4s') ||
    parsed.hostname === 'video.twimg.com'
  ) {
    return 'video';
  }

  if (
    X_API_HOSTS.has(parsed.hostname) &&
    (resourceType === 'xhr' ||
      resourceType === 'fetch' ||
      mimeType.includes('json') ||
      contentType.includes('json'))
  ) {
    return 'json';
  }

  if (
    parsed.hostname === 'pbs.twimg.com' &&
    parsed.pathname.startsWith('/media/') &&
    (resourceType === 'image' || mimeType.startsWith('image/') || contentType.startsWith('image/'))
  ) {
    return 'image';
  }

  return 'ignore';
}

export function getPbsMediaIdentity(url) {
  const parsed = parseUrl(url);
  if (!parsed || parsed.hostname !== 'pbs.twimg.com' || !parsed.pathname.startsWith('/media/')) {
    return null;
  }

  const rawName = parsed.pathname.slice('/media/'.length);
  if (!rawName) return null;
  const stem = rawName.replace(/\.[^.\/]+$/, '');
  return `pbs.twimg.com/media/${stem}`;
}

export function getHeader(headers, name) {
  if (!headers) return undefined;
  const target = name.toLowerCase();
  for (const [key, value] of Object.entries(headers)) {
    if (key.toLowerCase() === target) return value;
  }
  return undefined;
}

function parseUrl(url) {
  try {
    return new URL(url);
  } catch {
    return null;
  }
}
