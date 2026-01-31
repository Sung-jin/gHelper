import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import electron from 'vite-plugin-electron'
import renderer from 'vite-plugin-electron-renderer'
import path from 'path'

export default defineConfig({
  define: {
    'process.env.DISCORD_WEBHOOK_ETERNAL': JSON.stringify(process.env.DISCORD_WEBHOOK_ETERNAL),
  },
  plugins: [
    vue(),
    electron([
      {
        entry: 'src/main/main.ts',
        vite: {
          resolve: {
            alias: {
              '@main': path.resolve(__dirname, 'src/main'),
              '@util': path.resolve(__dirname, 'src/utils')
            }
          },
          build: {
            outDir: 'dist-electron',
          }
        },
        onstart(options) { options.startup() },
      },
      {
        entry: 'src/preload/preload.ts',
        vite: {
          build: {
            lib: {
              entry: 'src/preload/preload.ts',
              formats: ['cjs'],
              fileName: () => 'preload.js',
            },
            outDir: 'dist-electron',
            rollupOptions: {
              external: ['electron'],
              output: { format: 'cjs' }
            }
          }
        }
      }
    ]),
    renderer(),
  ],
  resolve: {
    alias: {
      '@main': path.resolve(__dirname, 'src/main'),
      '@render': path.resolve(__dirname, 'src/render'),
      '@util': path.resolve(__dirname, 'src/utils')
    }
  }
})
