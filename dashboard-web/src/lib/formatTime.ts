/**
 * Formats an ISO-8601 timestamp as an absolute date-time for display.
 *
 * The dashboard replays a historical dataset, so surfaces show when a transaction
 * actually happened (`event_time`) rather than its age against the wall clock — a
 * relative "N hours ago" degenerates into a five-figure hour count against a
 * September-2025 dataset.
 *
 * The locale and timeZone are pinned so output is deterministic across machines and
 * CI. UTC is deliberate: stored timestamps are UTC and the source CSV carried no
 * timezone, so converting to local/WIB would shift the displayed value away from what
 * is in the database.
 *
 * Note that `new Date('garbage')` does not throw — it yields an Invalid Date whose
 * `toLocaleString` returns the literal "Invalid Date". The explicit NaN guard returns
 * the raw input instead, so a malformed timestamp degrades to something diagnosable.
 *
 * Shared by TransactionMonitor (live feed) and AlertsPanel so the two panels cannot
 * drift apart.
 */
export function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString('en-GB', {
    timeZone: 'UTC',
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}
