import { describe, expect, it } from 'vitest';

describe('tooling', () => {
  it('runs vitest with jsdom', () => {
    const el = document.createElement('div');
    el.textContent = 'ok';
    expect(el.textContent).toBe('ok');
  });
});
