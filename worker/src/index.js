// Leaderboard API for games.michaelwarkentin.com, a Cloudflare Worker backed
// by a D1 (SQLite) database. The logic lives in leaderboard.js; this module
// only exports the Worker, because the runtime treats every export of the
// main module as an entry point. See worker/README.md for setup.

import { corsHeaders, handle, json } from './leaderboard.js';

export default {
  async fetch(request, env) {
    try {
      return await handle(request, env);
    } catch (error) {
      console.error(error);
      return json({ error: 'server error' }, 500, corsHeaders(request, env));
    }
  },
};
