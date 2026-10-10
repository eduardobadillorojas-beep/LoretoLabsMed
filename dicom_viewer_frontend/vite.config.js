import { defineConfig } from 'vite';
import { resolve } from 'node:path';

export default defineConfig({
  base: '/static/core/dicom_viewer/',

  worker: {
    format: 'es',
  },

  build: {
    outDir: resolve(import.meta.dirname, '../core/static/core/dicom_viewer'),
    emptyOutDir: true,
    sourcemap: false,
    target: 'es2020',

    lib: {
      entry: resolve(import.meta.dirname, 'src/main.js'),
      formats: ['es'],
      fileName: () => 'mpr-viewer.js',
    },

    rollupOptions: {
      output: {
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
});
