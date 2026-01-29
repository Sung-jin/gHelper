import https from 'https';

export const sendDiscordMessage = (webhookUrl: string, payload: object): Promise<void> => {
  return new Promise((resolve, reject) => {
    if (!webhookUrl) {
      console.warn('[DiscordHelper] Webhook URL is missing.');
      return resolve();
    }

    const data = JSON.stringify(payload);
    const url = new URL(webhookUrl);

    const options = {
      hostname: url.hostname,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data),
      },
    };

    const req = https.request(options, (res) => {
      if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
        resolve();
      } else {
        reject(new Error(`[DiscordHelper] Failed with status code: ${res.statusCode}`));
      }
    });

    req.on('error', (error) => {
      console.error('[DiscordHelper] Request Error:', error);
      reject(error);
    });

    req.write(data);
    req.end();
  });
};