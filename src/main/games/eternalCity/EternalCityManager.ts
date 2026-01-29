import { BrowserWindow } from 'electron';
import { EngineManagerBase } from '@main/core/EngineManagerBase'
import { sendDiscordMessage } from '@util/discordHelper'
import { calculateEntryTime } from '@util/timeHelper'

export class EternalCityManager extends EngineManagerBase {
  private discordWebhookUrl = process.env.DISCORD_WEBHOOK_ETERNAL;

  protected handleData(parsed: any, window: BrowserWindow) {
    // 1. 해당 엔진의 데이터가 아니면 무시
    if (parsed.game !== 'eternal-city') return;

    // 2. sub_type에 따른 정밀한 로직 처리
    switch (parsed.sub_type) {
      case 'RAID_ALERT':
        window.webContents.send('raid-detected', {
          content: parsed.content,
          time: new Date().toLocaleTimeString()
        });
        const discordPayload = {
          content: `🚨 **[이터널시티 레이드 알림]**\n${parsed.content}`,
          username: "EternalCity Bot"
        };

        if (this.discordWebhookUrl) {
          sendDiscordMessage(this.discordWebhookUrl, discordPayload).catch(console.error);
        }

        break;

      case 'TIME_SYNC':
        // 기존의 시간 계산 로직 복구
        const entryInfo = calculateEntryTime(parsed.server_time);
        window.webContents.send('entry-timer', entryInfo);
        break;

      default:
        // 일반 로그 처리 (LOG/STATUS 타입 등)
        window.webContents.send('log-update', parsed.content || parsed);
        break;
    }
  }

  protected handleRawData(raw: string, window: BrowserWindow) {
    // JSON 파싱에 실패한 일반 print문 등 처리
    window.webContents.send('log-update', raw);
  }

  protected handleError(error: string, window: BrowserWindow) {
    // 파이썬 stderr 발생 시 처리
    window.webContents.send('status-update', `Sniffer Error: ${error}`);
  }
}