// The games-share Worker: link-preview cards for Letterfield finds. The
// routes live in app.js; this module only sets up resvg and its fonts, which
// need Workers' wasm and data imports (see wrangler.toml's rules).

import { initWasm, Resvg } from '@resvg/resvg-wasm';
import wasm from '@resvg/resvg-wasm/index_bg.wasm';
import big from '../fonts/BigShouldersDisplay-800.ttf';
import mono4 from '../fonts/MartianMono-400.ttf';
import mono5 from '../fonts/MartianMono-500.ttf';
import ui5 from '../fonts/SchibstedGrotesk-500.ttf';
import ui6 from '../fonts/SchibstedGrotesk-600.ttf';
import { handle } from './app.js';
import { renderer } from './render.js';

const render = renderer(() => initWasm(wasm), Resvg, [big, mono4, mono5, ui5, ui6]);

export default {
  async fetch(request, env, ctx) {
    try {
      return await handle(request, env, ctx, render);
    } catch (error) {
      console.error({ share: 'failed', error: String(error) });
      return new Response('server error', { status: 500 });
    }
  },
};
