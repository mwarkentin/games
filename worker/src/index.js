// Leaderboard, War room and Letterfield survey API for
// games.michaelwarkentin.com, a Cloudflare Worker backed by a D1 (SQLite)
// database and Durable Objects: one per War room, and one per sector of
// Letterfield's map plus an Atlas. The logic lives in leaderboard.js, war.js
// and survey.js; this module only exports the Worker and the Durable Object
// classes, because the runtime treats every export of the main module as an
// entry point. See worker/README.md for setup.

import { corsHeaders, handle, json } from './leaderboard.js';
import { routeSurvey } from './survey.js';
import { handleWar } from './war.js';

export { Atlas, Sector } from './survey.js';
export { WarRoom } from './war.js';

export default {
  async fetch(request, env) {
    try {
      if (new URL(request.url).pathname.startsWith('/v1/war/')) return await handleWar(request, env);
      const survey = routeSurvey(request, env);
      return await (survey ?? handle(request, env));
    } catch (error) {
      console.error(error);
      return json({ error: 'server error' }, 500, corsHeaders(request, env));
    }
  },
};
