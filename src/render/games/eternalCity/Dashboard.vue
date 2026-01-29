<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  targetProcess: { name: string; pids: number[] } | null,
  managerId: string
}>()

const emit = defineEmits(['stop'])

const logs = ref<string[]>([])
const raidLogs = ref<any[]>([])
const displayCountdown = ref("00:00")
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
.raid-list, .log-list { font-size: 11px; overflow-y: auto; flex: 1; }
.raid-item, .log-item { border-bottom: 1px solid #2a2a2a; padding: 2px 0; }
</style>