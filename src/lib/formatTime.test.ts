import { describe, expect, it } from 'vitest';
import { formatTime } from './formatTime';

// The month is matched as Sep/Sept because en-GB's short form for September is
// CLDR-version dependent; day, year and time are pinned exactly.
const SEPT_1_1100 = /^01 Sept?\.? 2025, 11:00$/;

describe('formatTime', () => {
  it('renders an absolute UTC date-time, not a relative age', () => {
    expect(formatTime('2025-09-01T11:00:00+00:00')).toMatch(SEPT_1_1100);
    expect(formatTime('2025-09-01T11:00:00+00:00')).not.toMatch(/ago/);
  });

  it('accepts both the Z and +00:00 ISO spellings identically', () => {
    expect(formatTime('2025-09-03T14:22:00Z')).toBe(formatTime('2025-09-03T14:22:00+00:00'));
  });

  it('renders in UTC regardless of the offset used in the input', () => {
    // 18:00+07:00 is 11:00 UTC — the displayed value must be the UTC one, matching
    // what is stored in the database rather than a local/WIB reading.
    expect(formatTime('2025-09-01T18:00:00+07:00')).toMatch(SEPT_1_1100);
  });

  it('returns the raw input for an unparseable timestamp', () => {
    // new Date('garbage') does not throw; it yields Invalid Date, whose
    // toLocaleString would render the literal string "Invalid Date" to the user.
    expect(formatTime('not-a-date')).toBe('not-a-date');
    expect(formatTime('')).toBe('');
  });
});
