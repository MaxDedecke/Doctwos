import { AxiosHeaders, type AxiosResponse } from 'axios';

/** Build a complete Axios envelope while letting each mocked endpoint check its payload type. */
export function axiosResponse<T>(data: T): AxiosResponse<T, unknown> {
  return { data, status: 200, statusText: 'OK', headers: {}, config: { headers: new AxiosHeaders() } };
}
