<script setup lang="ts">
import { ref, onMounted } from 'vue'

const isMonitoring = ref(false)
const statusMessage = ref('')
const statusType = ref<'info' | 'error' | 'success'>('info')
const logs = ref<string[]>([])

// 알림 메시지 설정 함수
const setStatus = (msg: string, type: 'info' | 'error' | 'success' = 'info') => {
  statusMessage.value = msg
  statusType.value = type
}

const startMonitor = async () => {
  if (!selectedPid.value) return setStatus('프로세스를 선택해주세요.', 'error')

  logs.value = []
  setStatus('모니터링 시작 중...', 'info')

  const result = await (window as any).electronAPI.startMonitoring(selectedPid.value)

  if (result.success) {
    isMonitoring.value = true
    setStatus('모니터링 중: 패킷이 파일에 기록되고 있습니다.', 'success')
  } else {
    // 권한 부족이나 실행 실패 시 에러 메시지 처리
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

// 메인 프로세스로부터 상태 메시지 수신
onMounted(() => {
  (window as any).electronAPI.onStatusUpdate((msg: string) => {
    if (msg.includes('Permission denied') || msg.includes('Npcap')) {
      setStatus(`권한 오류: 관리자 권한으로 실행하거나 Npcap을 확인하세요.`, 'error')
    }
  })
})
</script>

<template>
  <div style="padding: 20px;">
    <div v-if="statusMessage" :class="['status-bar', statusType]">
      {{ statusMessage }}
    </div>

    <div class="controls">
      <button v-if="!isMonitoring" @click="startMonitor">감시 시작</button>
      <button v-else @click="stopMonitor" class="stop-btn">감시 중지</button>
    </div>
  </div>
</template>

<style scoped>
.status-bar {
  padding: 10px;
  margin-bottom: 15px;
  border-radius: 4px;
  font-weight: bold;
}
.info { background: #e3f2fd; color: #1976d2; }
.error { background: #ffebee; color: #c62828; border: 1px solid #c62828; }
.success { background: #e8f5e9; color: #2e7d32; }
.stop-btn { background: #d32f2f; color: white; }
</style>