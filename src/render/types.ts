export interface PacketLog {
  type: 'status' | 'packet' | 'alert';
  content: string;
  timestamp: number;
}