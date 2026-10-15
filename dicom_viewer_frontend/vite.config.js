import { defineConfig } from 'vite';
import { resolve } from 'node:path';

export default defineConfig({
  base: '/static/core/dicom_viewer/',

  resolve: {
    alias: {
      events: resolve(import.meta.dirname, 'node_modules/events/events.js'),
      url: resolve(import.meta.dirname, 'node_modules/url/url.js'),
    },
  },

  worker: {
    format: 'es',
  },

  build: {
    outDir: resolve(import.meta.dirname, '../core/static/core/dicom_viewer'),
    emptyOutDir: true,
    sourcemap: false,
    target: 'es2020',

    lib: {
      entry: {
        'mpr-viewer': resolve(import.meta.dirname, 'src/main.js'),
        'public-viewer': resolve(import.meta.dirname, 'src/public.js'),
      },
      formats: ['es'],
      fileName: (format, entryName) => `${entryName}.js`,
    },

    rollupOptions: {
      output: {
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
});
