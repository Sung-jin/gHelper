export interface EntryTimeInfo {
  targetTs: number;
  remainingSeconds: number;
  displayTime: string;
  isExpired: boolean;
}

/**
 * 서버 타임스탬프를 기준으로 10분 뒤의 입장 시간을 계산
 * @param serverTs 패킷에서 추출된 서버 시간 (단위: 초)
 */
export const calculateEntryTime = (serverTs: number): EntryTimeInfo => {
  const ENTRY_WINDOW = 10 * 60; // 10분 (600초)
  const targetTs = serverTs + ENTRY_WINDOW;
  const now = Math.floor(Date.now() / 1000);

  const diff = targetTs - now;
  const isExpired = diff <= 0;

  // 남은 시간을 MM:SS 형식으로 변환
  const mins = Math.floor(Math.abs(diff) / 60);
  const secs = Math.abs(diff) % 60;
  const displayTime = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;

  return {
    targetTs,
    remainingSeconds: diff,
    displayTime,
    isExpired
  };
};