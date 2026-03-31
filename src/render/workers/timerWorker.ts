let timerId: ReturnType<typeof setInterval> | null = null;

self.onmessage = (e) => {
  if (e.data.action === 'START') {
    if (timerId) clearInterval(timerId);

    timerId = setInterval(() => {
      self.postMessage({ action: 'TICK' });
    }, 1000);
  } else if (e.data.action === 'STOP') {
    if (timerId) clearInterval(timerId);
    timerId = null;
  }
};