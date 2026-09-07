import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/postcss';
import { fileURLToPath, URL } from 'node:url';
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': fileURLToPath(new URL('.', import.meta.url)) } },
  css: { postcss: { plugins: [tailwindcss()] } },
  build: {
    rolldownOptions: {
      output: {
        manualChunks: (id: string) =>
          id.includes('/node_modules/three/') ? 'three' : undefined,
      },
    },
  },
});
