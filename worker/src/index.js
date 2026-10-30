// Leaderboard API for games.michaelwarkentin.com, a Cloudflare Worker backed
// by a D1 (SQLite) database, and Letterfield's shared survey, a Durable Object
// per sector of its map plus one Atlas. The logic lives in leaderboard.js and
// survey.js; this module only exports the Worker and the Durable Object
// classes, because the runtime treats every export of the main module as an
// entry point. See worker/README.md for setup.

import { corsHeaders, handle, json } from './leaderboard.js';
import { routeSurvey } from './survey.js';

export { Atlas, Sector } from './survey.js';

export default {
  async fetch(request, env) {
    try {
      const survey = routeSurvey(request, env);
      return await (survey ?? handle(request, env));
    } catch (error) {
      console.error(error);
      return json({ error: 'server error' }, 500, corsHeaders(request, env));
    }
  },
};
