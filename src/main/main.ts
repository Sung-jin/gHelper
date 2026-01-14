import { app, BrowserWindow, ipcMain } from 'electron';
import * as path from 'path';
import { spawn, ChildProcess } from 'child_process';
import * as fs from 'fs';
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
let mainWindow: BrowserWindow | null = null;
let pythonProcess: ChildProcess | null = null;

// 1. 로그 저장 설정 (yyyy-MM-dd.log)
const getLogFilePath = () => {
  const logDir = path.join(app.getPath('userData'), 'logs'); // 사용자 데이터 폴더 내 logs
  if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });

  const today = new Date().toISOString().split('T')[0];
  return path.join(logDir, `${today}.log`);
};

const appendLogToFile = (message: string) => {
  const logPath = getLogFilePath();
  const timestamp = new Date().toLocaleTimeString();
  fs.appendFileSync(logPath, `[${timestamp}] ${message}\n`);
};

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1000,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (!app.isPackaged && process.env.NODE_ENV === 'development') {
    // 개발 모드: Vite 개발 서버 연결
    mainWindow.loadURL('http://localhost:5173');
  } else {
    // 프로덕션 모드: 빌드된 index.html 파일을 직접 로드
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }
}

// 2. 프로세스 목록 가져오기 (Windows/Mac 공용)
ipcMain.handle('get-process-list', async () => {
  return new Promise((resolve) => {
    const command = process.platform === 'win32'
      ? 'tasklist /fo csv /nh'
      : 'ps -ax -o pid,comm';

    const proc = spawn(command, { shell: true });
    let output = '';

    proc.stdout.on('data', (data) => { output += data.toString(); });
    proc.on('close', () => {
      const lines = output.trim().split('\n');
      const processList = lines.map(line => {
        if (process.platform === 'win32') {
          const parts = line.split('","');
          return { pid: parseInt(parts[1]), name: parts[0].replace(/"/g, '') };
        } else {
          const parts = line.trim().split(/\s+/);
          return { pid: parseInt(parts[0]), name: parts.slice(1).join(' ') };
        }
      }).filter(p => !isNaN(p.pid));
      resolve(processList);
    });
  });
});

// 3. 모니터링 시작 (Python 엔진 실행)
ipcMain.handle('start-monitoring', async (_event, pid: number) => {
  if (pythonProcess) {
    pythonProcess.kill();
  }

  // 프로젝트 루트 경로 확보 (dist-electron 기준이 아닌 실행 경로 기준)
  const PROJECT_ROOT = app.isPackaged
    ? process.resourcesPath
    : process.cwd();

  // 가상환경 내 파이썬 실행 파일 경로 설정
  const venvPath = app.isPackaged
    ? path.join(PROJECT_ROOT, 'engine', 'venv')
    : path.join(PROJECT_ROOT, 'engine', 'venv');

  const pythonExec = process.platform === 'win32'
    ? path.join(venvPath, 'Scripts', 'python.exe')
    : path.join(venvPath, 'bin', 'python');

  const scriptPath = path.join(PROJECT_ROOT, 'engine', 'monitor.py');

  try {
    pythonProcess = spawn(pythonExec, [scriptPath, pid.toString()]);

    // 표준 출력 (로그 데이터)
    pythonProcess.stdout?.on('data', (data) => {
      const line = data.toString().trim();
      if (line) {
        mainWindow?.webContents.send('log-update', line); // UI 전송
        appendLogToFile(line); // 파일 저장
      }
    });

    // 표준 에러 (권한 오류 등 상태값)
    pythonProcess.stderr?.on('data', (data) => {
      const errorMsg = data.toString();
      mainWindow?.webContents.send('status-update', errorMsg);
      appendLogToFile(`ERROR: ${errorMsg}`);
    });

    return { success: true };
  } catch (err: any) {
    return { success: false, error: err.message };
  }
});

// 4. 모니터링 중지
ipcMain.handle('stop-monitoring', async () => {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
    return true;
  }
  return false;
});

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (pythonProcess) pythonProcess.kill();
  if (process.platform !== 'darwin') app.quit();
});