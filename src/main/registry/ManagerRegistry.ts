import { EternalCityManager } from '@main/games/eternalCity/EternalCityManager'

export interface ManagerConfig {
  id: string;
  label: string;
  processKeywords: string[];
  pluginPath: string;
  instance: any;
}

export const SUPPORTED_MANAGERS: ManagerConfig[] = [
  {
    id: 'eternal-city',
    label: '이터널시티 매니저',
    processKeywords: ['city.exe', 'eternalcity', 'eternal', 'city'],
    pluginPath: 'engine/plugins/eternal_city_parser.py',
    instance: new EternalCityManager()
  },
];

export const getManagerById = (id: string) => SUPPORTED_MANAGERS.find(m => m.id === id);
