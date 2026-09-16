/**
 * Phase P0-4C — the two display primitives the new Candidate surfaces share.
 *
 * Both already existed as private copies in `workspaceTabs.tsx` and
 * `LiteratureInspector.tsx`; rather than add a third and fourth copy, they live
 * here and the new modules import them. The older copies are deliberately left
 * alone — consolidating them would touch a committed, unrelated view for no
 * behavioural gain.
 */

/** `—` for a value the API legitimately reports as absent. Never a guess. */
export function orDash(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

/** `YYYY-MM-DD HH:mm` in local time, or `—` when the stamp is missing/unparsable. */
export function formatTimestamp(value: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
