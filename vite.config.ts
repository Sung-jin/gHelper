import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import electron from 'vite-plugin-electron'
import renderer from 'vite-plugin-electron-renderer'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  base: './',
  plugins: [
    vue(),
    electron([
      {
        entry: 'src/main/main.ts',
        onstart(options) {
          options.startup()
        },
      },
      {
        entry: 'src/preload/preload.ts',
        // 'onlog'는 타입 에러 방지를 위해 제거했습니다.
        vite: {
          build: {
            // Preload 스크립트가 CommonJS로 변환되도록 강제하는 핵심 설정입니다.
            lib: {
              entry: 'src/preload/preload.ts',
              formats: ['cjs'],
              fileName: () => 'preload.js',
            },
            outDir: 'dist-electron',
            rollupOptions: {
              external: ['electron'],
              output: {
                // 이 설정을 통해 파일 확장을 .js로 유지하면서 내부 문법은 CJS로 만듭니다.
                entryFileNames: 'preload.js',
                format: 'cjs'
              }
            }
          }
        }
      }
    ]),
    renderer(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src/render')
    }
  }
})