import { defineConfig } from 'vite';
import { FLOOR_DEFINITIONS } from './src/data/floors.ts';

// GitHub Pages serves project sites from a sub-path (here https://mball.co/gateway-map/).
// The deploy workflow sets BASE_PATH=/<repo>/; local dev and preview keep '/'.
const superconductorPreviewHost = process.env.AGENT_WEB_HOST;

export default defineConfig({
  base: process.env.BASE_PATH ?? '/',
  plugins: [{
    name: 'static-floor-pages',
    enforce: 'post',
    generateBundle(_options, bundle) {
      const index = bundle['index.html'];
      if (!index || index.type !== 'asset') throw new Error('Missing built index.html');
      // GitHub Pages needs real files for direct links; it has no SPA fallback.
      for (const [id] of FLOOR_DEFINITIONS) {
        this.emitFile({
          type: 'asset',
          fileName: `floor-${id}/index.html`,
          source: index.source,
        });
      }
    },
  }],
  server: {
    // Allow Superconductor's routed preview host while keeping Vite's default local-host checks.
    allowedHosts: superconductorPreviewHost ? [superconductorPreviewHost] : [],
  },
});
