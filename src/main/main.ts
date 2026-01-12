import { app, BrowserWindow, ipcMain } from 'electron'
import { spawn, ChildProcess } from 'child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import * as fs from 'fs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
let mainWindow: BrowserWindow | null = null
let pythonProcess: ChildProcess | null = null // 실시간 모니터링용 프로세스

// 실행 환경에 따른 자원(Resources) 경로 결정
const getResourcePath = (relativePath: string) => {
  return app.isPackaged
    ? path.join(process.resourcesPath, relativePath) // 빌드된 상태 (resources 폴더 내부)
    : path.join(app.getAppPath(), relativePath);    // 개발 상태 (프로젝트 루트)
}

function createWindow() {
  const isDev = !!process.env.VITE_DEV_SERVER_URL;

  // 빌드 구조상 main.js와 같은 위치에 preload.mjs 또는 preload.js가 있는지 확인
  // electron-vite-plugin은 보통 확장자를 .mjs나 .js로 빌드합니다.
  let preloadPath = path.join(__dirname, 'preload.js');

  // 만약 위 경로에 없다면 상위 폴더나 .mjs 확장자 등을 체크해봅니다.
  if (!fs.existsSync(preloadPath)) {
    preloadPath = path.join(__dirname, 'preload.mjs');
  }

  console.log("--- Path Debugging ---");
  console.log("Current __dirname:", __dirname);
  console.log("Target Preload Path:", preloadPath);
  console.log("File Exists?:", fs.existsSync(preloadPath));
  console.log("----------------------");

  mainWindow = new BrowserWindow({
    width: 1000,
    height: 800,
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    }
  })

  if (isDev) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL)
  } else {
    mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'))
  }
}

// 1. 프로세스 목록 가져오기 (단회성 실행)
ipcMain.handle('get-process-list', async () => {
  return new Promise((resolve, reject) => {
    const pythonPath = path.join(app.getAppPath(), 'engine/venv/bin/python');
    const scriptPath = path.join(app.getAppPath(), 'engine/utils.py');
    const py = spawn(pythonPath, [scriptPath]);

    let result = '';
    py.stdout.on('data', (data) => { result += data.toString(); });
    py.on('close', (code) => {
      if (code === 0) {
        try { resolve(JSON.parse(result)); }
        catch (e) { reject('JSON 파싱 에러'); }
      } else { reject(`실패 코드: ${code}`); }
    });
  });
});

// 2. 선택한 PID로 모니터링 시작 (지속적 실행)
ipcMain.handle('start-monitoring', async (_event, pid: number) => {
  if (pythonProcess) pythonProcess.kill()

  const isWin = process.platform === 'win32'

  // 1. OS에 따른 가상환경 내 파이썬 경로 설정
  const pythonBin = isWin
    ? 'Scripts/python.exe'
    : 'bin/python'

  const pythonPath = getResourcePath(path.join('engine', 'venv', pythonBin))
  const scriptPath = getResourcePath(path.join('engine', 'monitor.py'))

  console.log(`Executing: ${pythonPath} with script ${scriptPath}`)

  // 2. 프로세스 실행
  pythonProcess = spawn(pythonPath, [scriptPath, pid.toString()])

  pythonProcess.stdout?.on('data', (data) => {
    const message = data.toString()
    _event.sender.send('packet-data', message)
  })

  pythonProcess.stderr?.on('data', (data) => {
    const errorMsg = data.toString()
    console.error(`[Python Error]: ${errorMsg}`)

    // 권한 관련 핵심 키워드가 포함되어 있다면 UI에 알림
    if (errorMsg.includes('PermissionError') || errorMsg.includes('operation not permitted')) {
      mainWindow?.webContents.send('status-update', 'Permission denied')
    }
  })

  pythonProcess.on('error', (err) => {
    mainWindow?.webContents.send('status-update', `Failed to start: ${err.message}`)
  })

  return true
})

ipcMain.handle('stop-monitoring', async () => {
  if (pythonProcess) {
    pythonProcess.kill(); // 프로세스 살해(?)
    pythonProcess = null;  // 참조 초기화
    console.log('Monitoring process stopped.');
    return true;
  }
  return false;
});

app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  if (pythonProcess) pythonProcess.kill();
  if (process.platform !== 'darwin') app.quit();
});