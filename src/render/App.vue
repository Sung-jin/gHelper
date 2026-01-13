<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'

interface ProcessInfo {
  pid: number;
  name: string;
}

const isMonitoring = ref(false)
const statusMessage = ref('')
const statusType = ref<'info' | 'error' | 'success'>('info')
const logs = ref<string[]>([])
const processes = ref<ProcessInfo[]>([])
const selectedPid = ref<number | null>(null)
const searchQuery = ref('') // 필터 입력값

// 필터링된 프로세스 목록 (Computed)
const filteredProcesses = computed(() => {
  if (!searchQuery.value) return processes.value
  const query = searchQuery.value.toLowerCase()
  return processes.value.filter(proc =>
    proc.name.toLowerCase().includes(query) || proc.pid.toString().includes(query)
  )
})

const setStatus = (msg: string, type: 'info' | 'error' | 'success' = 'info') => {
  statusMessage.value = msg
  statusType.value = type
}

const refreshProcesses = async () => {
  try {
    const list = await (window as any).electronAPI.getProcessList()
    processes.value = list
  } catch (err) {
    setStatus('프로세스 목록을 불러오지 못했습니다.', 'error')
  }
}

const startMonitor = async () => {
  if (!selectedPid.value) return setStatus('프로세스를 선택해주세요.', 'error')
  logs.value = []
  setStatus('모니터링 시작 중...', 'info')

  const result = await (window as any).electronAPI.startMonitoring(selectedPid.value)
  if (result.success) {
    isMonitoring.value = true
    setStatus('모니터링 중: 데이터가 기록되고 있습니다.', 'success')
  } else {
    setStatus(`오류: ${result.error}`, 'error')
  }
}

const stopMonitor = async () => {
  const success = await (window as any).electronAPI.stopMonitoring()
  if (success) {
    isMonitoring.value = false
    setStatus('모니터링이 중지되었습니다.', 'info')
  }
}

onMounted(() => {
  refreshProcesses();
  (window as any).electronAPI.onStatusUpdate((msg: string) => {
    if (msg.includes('Permission denied') || msg.includes('Npcap')) {
      setStatus(`권한 오류: 관리자 권한으로 실행하거나 Npcap을 확인하세요.`, 'error')
    }
  });
  (window as any).electronAPI.onLogUpdate((log: string) => {
    logs.value.unshift(log)
    if (logs.value.length > 100) logs.value.pop()
  });
})
</script>

<template>
  <div class="container">
    <div v-if="statusMessage" :class="['status-bar', statusType]">
      {{ statusMessage }}
    </div>

    <div class="controls">
      <input
        v-model="searchQuery"
        placeholder="프로세스 이름 또는 PID 검색..."
        class="filter-input"
        :disabled="isMonitoring"
      />

      <select v-model="selectedPid" :disabled="isMonitoring" class="process-select">
        <option :value="null" disabled>프로세스 선택 ({{ filteredProcesses.length }}개)</option>
        <option v-for="proc in filteredProcesses" :key="proc.pid" :value="proc.pid">
          [{{ proc.pid }}] {{ proc.name.length > 30 ? proc.name.substring(0, 30) + '...' : proc.name }}
        </option>
      </select>

      <button @click="refreshProcesses" :disabled="isMonitoring" class="refresh-btn">🔄</button>
      <button v-if="!isMonitoring" @click="startMonitor" class="start-btn">시작</button>
      <button v-else @click="stopMonitor" class="stop-btn">중지</button>
    </div>

    <div class="log-container">
      <div v-if="logs.length === 0" class="no-log">Packet logs will appear here...</div>
      <div v-for="(log, index) in logs" :key="index" class="log-item">{{ log }}</div>
    </div>
  </div>
</template>

<style scoped>
.container { padding: 20px; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
.status-bar { padding: 10px; margin-bottom: 15px; border-radius: 4px; font-weight: bold; font-size: 0.85rem; }
.info { background: #e3f2fd; color: #1976d2; }
.error { background: #ffebee; color: #c62828; border: 1px solid #c62828; }
.success { background: #e8f5e9; color: #2e7d32; }

.controls { display: flex; gap: 8px; margin-bottom: 15px; align-items: center; width: 100%; }
.filter-input { width: 200px; padding: 8px; border-radius: 4px; border: 1px solid #ddd; }
.process-select { flex: 1; min-width: 0; max-width: 400px; padding: 8px; border-radius: 4px; border: 1px solid #ddd; background: white; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.refresh-btn { padding: 8px; background: #eee; border: 1px solid #ccc; border-radius: 4px; cursor: pointer; }
.start-btn { padding: 8px 20px; background: #2ecc71; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }
.stop-btn { padding: 8px 20px; background: #e74c3c; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }

.log-container {
  background: #2d2d2d; color: #69f0ae; padding: 12px;
  height: 450px; overflow-y: auto; border-radius: 4px; font-family: 'Consolas', monospace; font-size: 0.8rem;
  box-shadow: inset 0 0 10px rgba(0,0,0,0.5);
}
.log-item { border-bottom: 1px solid #3d3d3d; padding: 3px 0; }
.no-log { color: #555; text-align: center; margin-top: 200px; }
</style>