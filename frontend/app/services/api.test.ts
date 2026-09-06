import { api } from './api';
import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('api.fetch', () => {
  it('forwards native responses and includes session cookies', async () => {
    const response = new Response('ok', { status: 200 });
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal('fetch', fetchMock);

    await expect(api.fetch('/download')).resolves.toBe(response);
    expect(fetchMock).toHaveBeenCalledWith('/download', { credentials: 'include' });
  });

  it('notifies the application when a native request receives 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })));
    const unauthorized = vi.fn();
    window.addEventListener('doctus:unauthorized', unauthorized);

    await api.fetch('/stream');

    expect(unauthorized).toHaveBeenCalledOnce();
    window.removeEventListener('doctus:unauthorized', unauthorized);
  });
});
