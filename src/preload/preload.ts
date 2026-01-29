import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  getProcessList: () => ipcRenderer.invoke('get-process-list'),
  closeApp: () => ipcRenderer.send('app:close'),

  getSupportedManagers: () => ipcRenderer.invoke('get-supported-managers'),
  startEngine: (data: { pids: number[], managerId: string }) => ipcRenderer.invoke('engine:start', data),
  stopEngine: (managerId: string) => ipcRenderer.invoke('engine:stop', managerId),

  onStatusUpdate: (callback: any) => ipcRenderer.on('status-update', (_event, value) => callback(value)),
  onLogUpdate: (callback: any) => ipcRenderer.on('log-update', (_event, value) => callback(value)),
  onRaidDetected: (callback: any) => ipcRenderer.on('raid-detected', (_event, value) => callback(value)),
  onEntryTimer: (callback: any) => ipcRenderer.on('entry-timer', (_event, value) => callback(value)),
});