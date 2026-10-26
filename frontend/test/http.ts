import { AxiosHeaders, type AxiosResponse } from 'axios';

/** Build a complete Axios envelope while letting each mocked endpoint check its payload type. */
// eslint-disable-next-line no-restricted-syntax -- axios 1.20 typisiert config.data nach dem Request-Typ des Endpunkts
export function axiosResponse<T>(data: T): AxiosResponse<T, any> {
  return { data, status: 200, statusText: 'OK', headers: {}, config: { headers: new AxiosHeaders() } };
}
