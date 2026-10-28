export const record = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
export const records = (value: unknown) => Array.isArray(value) ? value.filter(item => item && typeof item === 'object' && !Array.isArray(item)).map(record) : [];
export const strings = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : typeof value === 'string' ? [value] : [];
export const text = (value: unknown): string => typeof value === 'string' || typeof value === 'number' ? String(value) : '';
export type OpenLine = (line: number) => void;
