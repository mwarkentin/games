// Leaderboard and War room API for games.michaelwarkentin.com, a Cloudflare
// Worker backed by a D1 (SQLite) database and, for War, a Durable Object per
// room. The logic lives in leaderboard.js and war.js; this module only exports
// the Worker and the Durable Object class, because the runtime treats every
// export of the main module as an entry point. See worker/README.md for setup.

import { corsHeaders, handle, json } from './leaderboard.js';
import { handleWar } from './war.js';

export { WarRoom } from './war.js';

export default {
  async fetch(request, env) {
    try {
      if (new URL(request.url).pathname.startsWith('/v1/war/')) return await handleWar(request, env);
      return await handle(request, env);
    } catch (error) {
      console.error(error);
      return json({ error: 'server error' }, 500, corsHeaders(request, env));
    }
  },
};
