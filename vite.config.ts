import { defineConfig } from 'vite';

// GitHub Pages serves project sites from a sub-path (here https://mball.co/gateway-map/).
// The deploy workflow sets BASE_PATH=/<repo>/; local dev and preview keep '/'.
export default defineConfig({
  base: process.env.BASE_PATH ?? '/',
});
