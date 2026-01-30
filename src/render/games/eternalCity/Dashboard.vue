<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import type { AnalysisLog } from '@main/games/eternalCity/EternalCityManager'

const props = defineProps<{
  targetProcess: { name: string; pids: number[] } | null,
  managerId: string
}>()

const emit = defineEmits(['stop'])

const logs = ref<string[]>([])
const raidLogs = ref<any[]>([])
const displayCountdown = ref('00:00')
const analysisLogs = ref<AnalysisLog[]>([])
const entryData = ref<any>(null)
let timerWorker: Worker | null = null

const validateAndStart = async () => {
  if (!props.targetProcess || !props.managerId) return

  setupListeners()

  try {
    // 범용 IPC: engine:start 호출
    const result = await (window as any).electronAPI.startEngine({
      pids: props.targetProcess.pids,
      managerId: props.managerId
    });

    if (result.success) {
      initWorker();
    } else {
      alert(`Error: ${result.error}`);
      emit('stop');
    }
  } catch (error) {
    console.error("IPC Start Error:", error);
  }
}

const setupListeners = () => {
  const api = (window as any).electronAPI
  api.onStatusUpdate((msg: string) => logs.value.unshift(`[System] ${msg}`))
  api.onLogUpdate((log: string) => {
    logs.value.unshift(log)
    if (logs.value.length > 30) logs.value.pop()
  })
  api.onAnalysisLog((log: AnalysisLog) => {
    analysisLogs.value.unshift({
      ...log,
      id: Date.now(),
    });

    if (analysisLogs.value.length > 7) {
      analysisLogs.value.pop();
    }
  })
  api.onRaidDetected((data: any) => raidLogs.value.unshift(data))
  api.onEntryTimer((info: any) => {
    entryData.value = info
    timerWorker?.postMessage({ action: 'START' })
  })
}

const stopAll = async () => {
  await (window as any).electronAPI.stopEngine(props.managerId)
  if (timerWorker) timerWorker.terminate()
  emit('stop')
}

const initWorker = () => {
  timerWorker = new Worker(new URL('../../workers/timerWorker.ts', import.meta.url))
  timerWorker.onmessage = () => {
    if (!entryData.value) return
    const diff = entryData.value.targetTs - Math.floor(Date.now() / 1000)
    if (diff <= 0) {
      displayCountdown.value = "READY"
      timerWorker?.postMessage({ action: 'STOP' })
    } else {
      const mins = Math.floor(diff / 60)
      const secs = diff % 60
      displayCountdown.value = `${mins}:${secs.toString().padStart(2, '0')}`
    }
  }
}

onMounted(validateAndStart)
onUnmounted(() => { if (timerWorker) timerWorker.terminate() })
</script>

<template>
  <div class="dashboard-container">
    <div class="header">
      <div class="target-info">
        <span class="label">Target:</span> {{ targetProcess?.name.split(/[\\/]/).pop() }}
      </div>
      <button @click="stopAll" class="btn-stop">Stop</button>
    </div>

    <div class="grid-layout">
      <div class="card timer">
        <div class="card-title">Timer</div>
        <div class="timer-val">{{ displayCountdown }}</div>

        <div class="analysis-history">
          <div class="history-header">
            <span>Local (Server TS)</span>
            <span>Content</span>
          </div>
          <div v-for="log in analysisLogs" :key="log.id" class="history-item">
          <span class="history-time">
            {{ log.localTime }}
            <small v-if="log.serverTs">({{ log.serverTs }})</small>
          </span>
          <span class="history-content" :title="log.raw">{{ log.content }}</span>
          </div>
        </div>
      </div>
      <div class="card raids">
        <div class="card-title">Raids</div>
        <div class="raid-list">
          <div v-for="(r, i) in raidLogs" :key="i" class="raid-item">{{ r.time }} - {{ r.content }}</div>
        </div>
      </div>
      <div class="card logs">
        <div class="card-title">Logs</div>
        <div class="log-list">
          <div v-for="(log, i) in logs" :key="i" class="log-item">{{ log }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard-container { display: flex; flex-direction: column; gap: 10px; height: 100%; }
.header { display: flex; justify-content: space-between; align-items: center; background: #1a1a1a; padding: 8px; border-radius: 4px; }
.target-info { font-size: 12px; font-weight: bold; color: #2ecc71; }
.pid-count { color: #888; margin-left: 5px; }
.btn-stop { background: #e74c3c; border: none; color: white; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 11px; }
.grid-layout { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; flex: 1; overflow: hidden; }
.card { background: #1e1e1e; border: 1px solid #333; padding: 10px; border-radius: 4px; display: flex; flex-direction: column; }
.logs { grid-column: span 2; height: 120px; }
.card-title { font-size: 10px; color: #666; text-transform: uppercase; margin-bottom: 5px; }
.timer-val { font-size: 24px; text-align: center; color: #f1c40f; font-family: monospace; flex: 1; display: flex; align-items: center; justify-content: center; }
.analysis-history { margin-top: 12px; background: rgba(0, 0, 0, 0.2); border-radius: 4px; padding: 8px; }
.history-header { display: flex; justify-content: space-between; font-size: 0.65rem; color: #888; margin-bottom: 4px; border-bottom: 1px solid #333; }
.history-item { font-size: 0.75rem; display: flex; flex-direction: column; margin-bottom: 6px; border-bottom: 1px dashed #333; }
.history-time { color: #4db3ff; font-family: 'Courier New', monospace; font-weight: bold; }
.history-time small { color: #aaa; font-weight: normal; margin-left: 4px; }
.history-content { color: #eee; word-break: break-all; }
.raid-list, .log-list { font-size: 11px; overflow-y: auto; flex: 1; }
.raid-item, .log-item { border-bottom: 1px solid #2a2a2a; padding: 2px 0; }
</style>