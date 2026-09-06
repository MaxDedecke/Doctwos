import { describe, expect, it } from 'vitest';
import { AxiosError, AxiosHeaders } from 'axios';
import { apiErrorDetail } from './apiError';

function errorWithDetail(detail: unknown) {
  return new AxiosError('request failed', 'ERR_BAD_REQUEST', undefined, undefined, {
    data: { detail }, status: 422, statusText: 'Unprocessable Entity',
    headers: {}, config: { headers: new AxiosHeaders() },
  });
}

describe('API error text', () => {
  it('returns a server message', () => {
    expect(apiErrorDetail(errorWithDetail('Kein Zugriff'))).toBe('Kein Zugriff');
  });
  it('does not send a FastAPI validation array into React text state', () => {
    expect(apiErrorDetail(errorWithDetail([{ loc: ['body', 'name'], msg: 'required' }]))).toBeUndefined();
  });
  it('leaves network and arbitrary thrown values to the caller fallback', () => {
    expect(apiErrorDetail(new AxiosError('Network Error'))).toBeUndefined();
    expect(apiErrorDetail(null)).toBeUndefined();
    expect(apiErrorDetail('failure')).toBeUndefined();
  });
});
