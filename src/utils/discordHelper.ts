import * as https from 'https';
import { IncomingMessage } from 'http';
import log from 'electron-log'

export const sendDiscordMessage = (webhookUrl: string, payload: any): Promise<void> => {
  return new Promise((resolve, reject) => {
    const url = new URL(webhookUrl);

    const options = {
      hostname: url.hostname,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    };

    // 2. res 인자에 IncomingMessage 타입 지정
    const req = https.request(options, (res: IncomingMessage) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
          log.info(`[Discord Helper] SEND DONE. status: ${res.statusCode} data: ${data} `);
          resolve();
        } else {
          log.error(`[Discord Helper] SEND ERROR. status ${res.statusCode} data: ${data} `);
          reject(new Error(`Status Code: ${res.statusCode}`));
        }
      });
    });

    // 3. error 인자에 Error 타입 지정
    req.on('error', (error: Error) => {
      log.error('[Discord Helper] ERROR: ', error);
      reject(error);
    });

    req.write(JSON.stringify(payload));
    req.end();
  });
};