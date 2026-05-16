import assert from 'node:assert/strict';
import test from 'node:test';

import { extractTweets } from '../../extension/lib/tweet_parser.mjs';

test('extracts tweet, author, text, and body photo media from GraphQL result objects', () => {
  const payload = {
    data: {
      home: {
        timeline: {
          instructions: [
            {
              entries: [
                {
                  content: {
                    itemContent: {
                      tweet_results: {
                        result: {
                          __typename: 'Tweet',
                          rest_id: '111',
                          legacy: {
                            full_text: 'hello image',
                            created_at: 'Wed May 01 10:00:00 +0000 2026',
                            extended_entities: {
                              media: [
                                {
                                  type: 'photo',
                                  media_url_https: 'https://pbs.twimg.com/media/Gabc123.jpg',
                                  expanded_url: 'https://x.com/a/status/111/photo/1',
                                },
                              ],
                            },
                          },
                          core: {
                            user_results: {
                              result: {
                                rest_id: '42',
                                legacy: {
                                  screen_name: 'alice',
                                  name: 'Alice',
                                },
                              },
                            },
                          },
                        },
                      },
                    },
                  },
                },
              ],
            },
          ],
        },
      },
    },
  };

  const tweets = extractTweets(payload);

  assert.equal(tweets.length, 1);
  assert.equal(tweets[0].id, '111');
  assert.equal(tweets[0].text, 'hello image');
  assert.equal(tweets[0].author.id, '42');
  assert.equal(tweets[0].author.screenName, 'alice');
  assert.deepEqual(tweets[0].mediaImages.map((item) => item.url), [
    'https://pbs.twimg.com/media/Gabc123.jpg',
  ]);
  assert.deepEqual(tweets[0].mediaImages.map((item) => item.identity), [
    'pbs.twimg.com/media/Gabc123',
  ]);
});

test('extracts quoted tweet body images as saveable tweet media', () => {
  const payload = {
    data: {
      threaded_conversation_with_injections_v2: {
        instructions: [
          {
            entries: [
              {
                content: {
                  itemContent: {
                    tweet_results: {
                      result: {
                        __typename: 'Tweet',
                        rest_id: '222',
                        legacy: {
                          full_text: 'quote wrapper',
                          quoted_status_id_str: '333',
                        },
                        quoted_status_result: {
                          result: {
                            __typename: 'Tweet',
                            rest_id: '333',
                            legacy: {
                              full_text: 'quoted image',
                              entities: {
                                media: [
                                  {
                                    type: 'photo',
                                    media_url_https:
                                      'https://pbs.twimg.com/media/Gquoted456?format=png&name=small',
                                  },
                                ],
                              },
                            },
                          },
                        },
                      },
                    },
                  },
                },
              },
            ],
          },
        ],
      },
    },
  };

  const tweets = extractTweets(payload);
  const byId = new Map(tweets.map((tweet) => [tweet.id, tweet]));

  assert.equal(byId.has('222'), true);
  assert.equal(byId.has('333'), true);
  assert.equal(byId.get('333').text, 'quoted image');
  assert.deepEqual(byId.get('333').mediaImages.map((item) => item.identity), [
    'pbs.twimg.com/media/Gquoted456',
  ]);
});

test('extracts author fields from current X user core objects', () => {
  const payload = {
    tweet_results: {
      result: {
        __typename: 'Tweet',
        rest_id: '555',
        legacy: {
          full_text: 'new user shape',
        },
        core: {
          user_results: {
            result: {
              __typename: 'User',
              rest_id: '1963492104807587840',
              core: {
                name: 'Hunter Bown',
                screen_name: 'goodhunt',
              },
              legacy: {
                entities: {
                  description: {},
                },
              },
            },
          },
        },
      },
    },
  };

  const tweets = extractTweets(payload);

  assert.equal(tweets.length, 1);
  assert.deepEqual(tweets[0].author, {
    id: '1963492104807587840',
    screenName: 'goodhunt',
    name: 'Hunter Bown',
  });
});

test('deduplicates repeated tweet result objects', () => {
  const tweet = {
    __typename: 'Tweet',
    rest_id: '444',
    legacy: { full_text: 'same tweet' },
  };

  assert.equal(extractTweets({ a: tweet, b: { tweet_results: { result: tweet } } }).length, 1);
});

test('ignores user result objects while walking GraphQL payloads', () => {
  const payload = {
    data: {
      user: {
        result: {
          __typename: 'User',
          rest_id: '19837372',
          legacy: {
            screen_name: 'someone',
            name: 'Someone',
            entities: {
              description: {
                urls: [],
              },
            },
          },
        },
      },
    },
  };

  assert.deepEqual(extractTweets(payload), []);
});
