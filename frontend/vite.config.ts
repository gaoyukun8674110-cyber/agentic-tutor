import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';
import tailwindcss from '@tailwindcss/vite';
import path from 'path';

const mathPackages = [
  '/react-markdown/',
  '/remark-math/',
  '/rehype-katex/',
  '/rehype-sanitize/',
  '/katex/',
  '/mdast-',
  '/micromark',
  '/hast-',
  '/unist-',
  '/vfile',
  '/property-information/',
  '/space-separated-tokens/',
  '/comma-separated-tokens/',
  '/decode-named-character-reference/',
];

function manualChunks(id: string) {
  if (!id.includes('/node_modules/')) {
    return undefined;
  }
  if (mathPackages.some((segment) => id.includes(segment))) {
    return 'math-rendering';
  }
  if (id.includes('/d3-') || id.includes('/victory-vendor/')) {
    return 'chart-vendor';
  }
  if (id.includes('/recharts/')) {
    return 'charts';
  }
  if (id.includes('/lucide-react/')) {
    return 'icons';
  }
  return undefined;
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
    setupFiles: ['./vitest.setup.ts'],
  },
  build: {
    target: 'esnext',
    outDir: 'dist',
    rollupOptions: {
      output: {
        manualChunks,
      },
    },
  },
});
