<script setup lang="ts">
import { ref, onMounted, computed, watch, markRaw, defineAsyncComponent } from 'vue'

// 동적 컴포넌트 로드
const EternalDashboard = defineAsyncComponent(() => import('@render/games/eternalCity/Dashboard.vue'))

interface ProcessGroup { name: string; pids: number[]; }
interface Manager { id: string; label: string; processKeywords: string[]; }

const isMonitoring = ref(false)
const processes = ref<ProcessGroup[]>([])
const supportedManagers = ref<Manager[]>([])
const selectedProcess = ref<ProcessGroup | null>(null)
const selectedManagerId = ref('')
const searchQuery = ref('')

const activeDashboard = computed(() => {
  if (selectedManagerId.value === 'eternal-city') return markRaw(EternalDashboard)
  return null
})

const refreshProcesses = async () => {
  const list = await (window as any).electronAPI.getProcessList()
  processes.value = list
}

onMounted(async () => {
  refreshProcesses()
  // TypeError 방지: API 존재 여부 확인 후 호출
  if ((window as any).electronAPI.getSupportedManagers) {
    supportedManagers.value = await (window as any).electronAPI.getSupportedManagers()
  }
})

watch(selectedProcess, (newProc) => {
  if (!newProc) return
  const procName = newProc.name.toLowerCase()
  const recommended = supportedManagers.value.find(m =>
    m.processKeywords.some(key => procName.includes(key.toLowerCase()))
  )
  if (recommended) selectedManagerId.value = recommended.id
})

const filteredProcesses = computed(() => {
  if (!searchQuery.value) return processes.value
  const query = searchQuery.value.toLowerCase()
  return processes.value.filter(p => p.name.toLowerCase().includes(query))
})

const handleConnect = () => {
  if (selectedProcess.value && selectedManagerId.value) isMonitoring.value = true
}

const handleStop = () => {
  isMonitoring.value = false
  selectedProcess.value = null
  selectedManagerId.value = ''
  refreshProcesses()
}

const formatName = (name: string) => name.split(/[\\/]/).pop()
const closeApp = () => (window as any).electronAPI.closeApp()
</script>

<template>
  <div class="app-wrapper">
    <header class="drag-handle">
      <span class="logo">gHelper</span>
      <button class="close-btn" @click="closeApp">×</button>
    </header>

    <main class="main-body">
      <div v-if="!isMonitoring" class="selector-container">
        <h2 class="title">Engine Selector</h2>

        <div class="control-grid mb-10">
          <input v-model="searchQuery" placeholder="Search..." class="widget-input" />
          <div class="select-box">
            <select v-model="selectedProcess" class="widget-select">
              <option :value="null" disabled>Select Process</option>
              <option v-for="p in filteredProcesses" :key="p.name" :value="p">
                {{ formatName(p.name) }} ({{ p.pids.length }})
              </option>
            </select>
          </div>
          <button @click="refreshProcesses" class="btn-icon">🔄</button>
          <div class="spacer"></div> </div>

        <div class="control-grid">
          <div class="manager-label">Manager</div>
          <div class="select-box">
            <select v-model="selectedManagerId" class="widget-select highlight">
              <option value="" disabled>Select Manager (Engine)</option>
              <option v-for="m in supportedManagers" :key="m.id" :value="m.id">
                {{ m.label }}
              </option>
            </select>
          </div>
          <div class="spacer"></div>
          <button @click="handleConnect" :disabled="!selectedProcess || !selectedManagerId" class="btn-primary">Connect</button>
        </div>
      </div>

      <component
        v-else
        :is="activeDashboard"
        :targetProcess="JSON.parse(JSON.stringify(selectedProcess))"
        :managerId="selectedManagerId"
        @stop="handleStop"
      />
    </main>
  </div>
</template>

<style>
/* 기존 전역 스타일 유지 및 투명화 방지 추가 */
html, body, #app {
  margin: 0 !important;
  padding: 0 !important;
  height: 100vh;
  width: 100vw;
  background: #121212; /* 검은색 배경 고정 */
  color: #eee;
  overflow: hidden;
  font-family: sans-serif;
}

.app-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #121212;
}

.drag-handle {
  height: 32px;
  background: #1a1a1a;
  -webkit-app-region: drag;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 12px;
  border-bottom: 1px solid #2d2d2d;
}

.close-btn {
  -webkit-app-region: no-drag;
  background: none; border: none; color: #888; font-size: 20px; cursor: pointer;
}

.main-body { flex: 1; padding: 15px; display: flex; flex-direction: column; background: #121212; }

.title { font-size: 18px; margin: 0 0 15px 0; font-weight: bold; }

.control-grid {
  display: grid;
  grid-template-columns: 80px 1fr 35px 70px;
  gap: 6px;
  align-items: center;
}

.mb-10 { margin-bottom: 10px; }

.widget-input, .widget-select {
  height: 32px;
  background: #252525;
  border: 1px solid #333;
  color: white;
  padding: 0 8px;
  border-radius: 4px;
  font-size: 12px;
  width: 100%;
  box-sizing: border-box;
}

.widget-select.highlight {
  border-color: #2ecc71; /* 추천 매니저 강조색 */
}

.manager-label {
  font-size: 11px;
  color: #888;
  text-align: right;
  padding-right: 5px;
}

.btn-icon { height: 32px; background: #333; border: none; color: white; border-radius: 4px; cursor: pointer; }
.btn-primary { height: 32px; background: #2ecc71; border: none; color: white; border-radius: 4px; font-weight: bold; cursor: pointer; font-size: 12px; }
.btn-primary:disabled { background: #2a2a2a; color: #555; }

.select-box { min-width: 0; }
</style>