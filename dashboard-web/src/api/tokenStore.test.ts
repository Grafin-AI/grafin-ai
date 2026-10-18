import { describe, expect, it } from 'vitest';
import { tokenStore } from './tokenStore';

describe('tokenStore', () => {
  it('persists and clears tokens', () => {
    expect(tokenStore.getAccess()).toBeNull();
    tokenStore.set({ access_token: 'a', refresh_token: 'r', token_type: 'bearer' });
    expect(tokenStore.getAccess()).toBe('a');
    expect(tokenStore.getRefresh()).toBe('r');
    tokenStore.clear();
    expect(tokenStore.getAccess()).toBeNull();
    expect(tokenStore.getRefresh()).toBeNull();
  });
});
