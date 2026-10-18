import type { TokenResponse } from './types';

const ACCESS = 'grafin.access';
const REFRESH = 'grafin.refresh';

export const tokenStore = {
  getAccess(): string | null {
    return localStorage.getItem(ACCESS);
  },
  getRefresh(): string | null {
    return localStorage.getItem(REFRESH);
  },
  set(tokens: Pick<TokenResponse, 'access_token' | 'refresh_token'>): void {
    localStorage.setItem(ACCESS, tokens.access_token);
    localStorage.setItem(REFRESH, tokens.refresh_token);
  },
  clear(): void {
    localStorage.removeItem(ACCESS);
    localStorage.removeItem(REFRESH);
  },
};
