// Leaderboard, War room and Letterfield survey API for
// games.michaelwarkentin.com, a Cloudflare Worker backed by a D1 (SQLite)
// database and Durable Objects: one per War room, and one per sector of
// Letterfield's map plus an Atlas. The logic lives in leaderboard.js, war.js,
// survey.js, survey-log.js, survey-social.js (who's surveying,
// and their emotes), survey-guild.js (guilds), players.js (one player on several
// devices) and define.js (what Letterfield's words mean);
// this module only exports the Worker and the Durable Object classes, because
// the runtime treats every export of the main module as an entry point. See
// worker/README.md for setup.

import { routeDefine } from './define.js';
import { corsHeaders, handle, json } from './leaderboard.js';
import { routeSurvey } from './survey.js';
import { routeLog } from './survey-log.js';
import { routeLinks } from './players.js';
import { routeGuilds } from './survey-guild.js';
import { routeSurveyors } from './survey-social.js';
import { handleWar } from './war.js';

export { Atlas, Sector } from './survey.js';
export { Guild } from './survey-guild.js';
export { WarRoom } from './war.js';

export default {
  async fetch(request, env) {
    try {
      if (new URL(request.url).pathname.startsWith('/v1/war/')) return await handleWar(request, env);
      const survey = routeSurvey(request, env) ?? routeSurveyors(request, env, corsHeaders, json) ?? routeGuilds(request, env) ?? routeLinks(request, env) ?? routeLog(request, env) ?? routeDefine(request, env);
      return await (survey ?? handle(request, env));
    } catch (error) {
      console.error(error);
      return json({ error: 'server error' }, 500, corsHeaders(request, env));
    }
  },
};
