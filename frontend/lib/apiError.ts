import { isAxiosError } from 'axios';

/** FastAPI detail can also be a validation-error array; only text belongs in a toast. */
export function apiErrorDetail(error: unknown): string | undefined {
  if (!isAxiosError<{ detail?: unknown }>(error)) return undefined;
  const detail = error.response?.data?.detail;
  return typeof detail === 'string' ? detail : undefined;
}
