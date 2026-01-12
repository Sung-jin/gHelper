import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electronAPI', {
  // 1. 프로세스 목록 요청
  getProcessList: () => ipcRenderer.invoke('get-process-list'),

  // 2. 모니터링 시작 요청 (PID 전달)
  startMonitoring: (pid: number) => ipcRenderer.invoke('start-monitoring', pid),
  stopMonitoring: () => ipcRenderer.invoke('stop-monitoring'),

  // 3. 메인에서 오는 실시간 패킷 데이터를 받기 위한 리스너
  onPacketData: (callback: (data: string) => void) =>
    ipcRenderer.on('packet-data', (_event, value) => callback(value))
})