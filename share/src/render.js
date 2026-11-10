// SVG to PNG with resvg, given its wasm (started once, on the first card) and
// the fonts. Kept apart from index.js so Node tests can build one too.
export function renderer(init, Resvg, fonts) {
  const fontBuffers = fonts.map((f) => new Uint8Array(f));
  let ready = null;
  return async (svg) => {
    ready ??= init().catch((error) => { ready = null; throw error; });
    await ready;
    return new Resvg(svg, {
      fitTo: { mode: 'original' },
      font: { fontBuffers, loadSystemFonts: false, defaultFontFamily: 'Schibsted Grotesk' },
    }).render().asPng();
  };
}
