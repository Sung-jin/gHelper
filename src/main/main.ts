import { app, BrowserWindow, ipcMain } from 'electron';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';
import { EternalCityManager } from './games/eternalCity/EternalCityManager.js';
import { getManagerById, SUPPORTED_MANAGERS } from '@main/registry/ManagerRegistry'

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let mainWindow: BrowserWindow | null = null;
const eternalManager = new EternalCityManager();
const isWin = process.platform === 'win32';

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 500,
    height: 450,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (!app.isPackaged && process.env.NODE_ENV === 'development') {
    mainWindow.loadURL('http://localhost:5173');
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }
}

const getPaths = () => {
  const PROJECT_ROOT = app.isPackaged ? process.resourcesPath : process.cwd();
  const venvPath = path.join(PROJECT_ROOT, 'engine', 'venv');

  return {
    PROJECT_ROOT,
    pythonExec: process.platform === 'win32'
      ? path.join(venvPath, 'Scripts', 'python.exe')
      : path.join(venvPath, 'bin', 'python'),
    snifferPath: path.join(PROJECT_ROOT, 'engine', 'core', 'sniffer.py')
  };
};

// --- IPC 핸들러 ---

ipcMain.handle('get-process-list', async () => {
  return new Promise((resolve) => {
    const command = isWin ? 'tasklist /fo csv /nh' : 'ps -ax -o pid,comm';

    const proc = spawn(command, { shell: true });
    let output = '';

    proc.stdout.on('data', (data) => { output += data.toString(); });
    proc.on('close', () => {
      const lines = output.trim().split('\n');
      const grouped = new Map<string, { name: string; pids: number[] }>();

      lines.forEach(line => {
        let name = '';
        let pid = 0;

        if (isWin) {
          const parts = line.split('","');
          if (parts.length >= 2) {
            name = parts[0].replace(/"/g, '');
            pid = parseInt(parts[1].replace(/"/g, ''));
          }
        } else {
          const parts = line.trim().split(/\s+/);
          if (parts.length >= 2) {
            pid = parseInt(parts[0]);
            name = parts.slice(1).join(' ');
          }
        }

        if (name && !isNaN(pid)) {
          if (!grouped.has(name)) {
            grouped.set(name, { name, pids: [pid] });
          } else {
            grouped.get(name)!.pids.push(pid);
          }
        }
      });

      resolve(Array.from(grouped.values()).sort((a, b) => a.name.localeCompare(b.name)));
    });
  });
});

ipcMain.handle('get-supported-managers', () => {
  return SUPPORTED_MANAGERS.map(({ id, label, processKeywords }) => ({ id, label, processKeywords }));
});

// 2. 범용 엔진 시작 핸들러
ipcMain.handle('engine:start', async (_event, { pids, managerId }) => {
  if (!mainWindow) return { success: false, error: 'Window not found' };

  const config = getManagerById(managerId);
  if (!config) return { success: false, error: '유효하지 않은 매니저입니다.' };

  const { pythonExec, snifferPath, PROJECT_ROOT } = getPaths();
  const pluginPath = path.join(PROJECT_ROOT, config.pluginPath);

  try {
    // 선택된 매니저 인스턴스 실행
    config.instance.start(pythonExec, snifferPath, [pids[0].toString(), pluginPath], mainWindow);

    mainWindow.webContents.send('status-update', `${config.label} 시작됨 (PID: ${pids[0]})`);
    return { success: true };
  } catch (err: any) {
    console.error('Engine Start Error:', err);
    return { success: false, error: err.message };
  }
});

ipcMain.handle('engine:stop', async (_event, managerId) => {
  const config = getManagerById(managerId);
  config?.instance.stop();
  return true;
});

// 앱 종료 핸들러
ipcMain.on('app:close', () => app.quit());

app.whenReady().then(createWindow);
app.on('window-all-closed', () => {
  eternalManager.stop();
  if (process.platform !== 'darwin') app.quit();
});