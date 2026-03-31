import { spawn, ChildProcess } from 'child_process';
import { BrowserWindow } from 'electron';
import log from 'electron-log'

export abstract class EngineManagerBase {
  protected pythonProcess: ChildProcess | null = null;

  public start(pythonExec: string, scriptPath: string, args: string[], window: BrowserWindow) {
    this.stop();

    // '-u' 옵션으로 버퍼링 제거
    this.pythonProcess = spawn(pythonExec, ['-u', scriptPath, ...args]);

    this.pythonProcess.stdout?.on('data', (data: Buffer) => {
      const lines = data.toString().split('\n');
      lines.forEach((line) => {
        const trimmed = line.trim();
        if (!trimmed) return;

        try {
          const parsed = JSON.parse(trimmed);
          // 1. 성공적으로 파싱된 객체를 자식에게 전달
          this.handleData(parsed, window);
        } catch (e) {
          // 2. 파싱 실패한 원문(Raw) 문자열도 그대로 자식에게 전달 (판단은 자식이 함)
          this.handleRawData(trimmed, window);
        }
      });
    });

    this.pythonProcess.on('error', (error) => {
      log.error(`[Python process error]`, error)
    })
    this.pythonProcess.stderr?.on('data', (data) => {
      log.error(`[Python stderr]`, data);
      this.handleError(data.toString(), window);
    });
  }

  public stop() {
    if (this.pythonProcess) {
      this.pythonProcess.kill();
      this.pythonProcess = null;
    }
  }

  // 자식 클래스에서 반드시 구현해야 할 추상 메서드들
  protected abstract handleData(parsed: any, window: BrowserWindow): void;
  protected abstract handleRawData(raw: string, window: BrowserWindow): void;
  protected abstract handleError(error: string, window: BrowserWindow): void;
}