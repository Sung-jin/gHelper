import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electronAPI', {
  getProcessList: () => ipcRenderer.invoke('get-process-list'), // 프로세스 목록 가져오기
  startMonitoring: (pid: number) => ipcRenderer.invoke('start-monitoring', pid),
  stopMonitoring: () => ipcRenderer.invoke('stop-monitoring'),
  onStatusUpdate: (callback: any) => ipcRenderer.on('status-update', (_event, value) => callback(value)),
  onLogUpdate: (callback: any) => ipcRenderer.on('log-update', (_event, value) => callback(value))
})