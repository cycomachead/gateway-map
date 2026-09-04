import { defineConfig } from 'vite';

// GitHub Pages serves project sites from a sub-path (here https://mball.co/gateway-map/).
// The deploy workflow sets BASE_PATH=/<repo>/; local dev and preview keep '/'.
const superconductorPreviewHost = process.env.AGENT_WEB_HOST;

export default defineConfig({
  base: process.env.BASE_PATH ?? '/',
  server: {
    // Allow Superconductor's routed preview host while keeping Vite's default local-host checks.
    allowedHosts: superconductorPreviewHost ? [superconductorPreviewHost] : [],
  },
});
