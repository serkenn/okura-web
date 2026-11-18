// 線画のアイコン（自作。24x24・線 1.75）。道（path）は iconPaths.js
import { P } from './iconPaths.js';

export type IconName = string;

export function Icon({ name, size = 18, cls = '' }: { name: IconName; size?: number; cls?: string }) {
  const d = (P as Record<string, string>)[name] || (P as Record<string, string>).dots;
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth={1.75}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={`ic ${cls}`}>
      <path d={d} />
    </svg>
  );
}
