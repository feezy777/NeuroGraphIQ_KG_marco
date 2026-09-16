/**
 * Discovery View resolution for display — persisted strategy identifier to label.
 *
 * PRESENTATION ONLY. It deliberately does NOT restate the backend's scientific
 * definitions (`app/llm_discovery_views.py`): those are instructions to the
 * model about what to look for, not copy for a person reading a run list. This
 * module answers exactly one question — "which discovery VIEW produced this
 * run?" — from the value the run actually persisted, and nothing else.
 *
 * The persisted encoding is `G4HR1/<VIEW>` in `query_strategy_version`. The
 * label is looked up from the view TOKEN, never parsed out of prose, so an
 * unknown or future strategy is reported as unknown rather than misfiled as one
 * of the four. Silence (null) is the LEGACY run and is labelled as such — the
 * one thing it must never be shown as is a view it did not use.
 */
const SEPARATOR = '/'

/** The strategy prefix this UI understands. Mirrors the backend constant. */
export const G4_STRATEGY_VERSION = 'G4HR1'

/** The four frozen G4 views, in pilot order. */
export const G4_DISCOVERY_VIEWS: readonly string[] = [
  'NAMED_CLASSIC_CIRCUITS',
  'LOCAL_INTRINSIC_CIRCUITS',
  'AFFERENT_CIRCUITS',
  'EFFERENT_CIRCUITS',
]

/** i18n key per persisted view token. Labels only — never the science. */
export const DISCOVERY_VIEW_LABEL_KEYS: Record<string, string> = {
  NAMED_CLASSIC_CIRCUITS: 'knowledgeProduction.discoveryView.namedClassic',
  LOCAL_INTRINSIC_CIRCUITS: 'knowledgeProduction.discoveryView.localIntrinsic',
  AFFERENT_CIRCUITS: 'knowledgeProduction.discoveryView.afferent',
  EFFERENT_CIRCUITS: 'knowledgeProduction.discoveryView.efferent',
}

/** The legacy single-pass run: no view was ever recorded. */
export const LEGACY_DISCOVERY_LABEL_KEY = 'knowledgeProduction.discoveryView.legacy'

/** A strategy this UI cannot name. Shown WITH its raw value, never guessed at. */
export const UNKNOWN_DISCOVERY_LABEL_KEY = 'knowledgeProduction.discoveryView.unknown'

/**
 * The backend spells its legacy default `GENERAL_DISCOVERY`, but never persists
 * it (it resolves to NULL). Recognised here as a defensive alias of legacy, not
 * as a fifth view — it is the same "no view" fact in a different spelling.
 */
const LEGACY_ALIAS = 'GENERAL_DISCOVERY'

export type ResolvedDiscoveryView = {
  /** The canonical view token, or null when this run used no view. */
  view: string | null
  /** i18n key for the user-facing label. */
  labelKey: string
  /** The strategy version token, when the identifier carried one. */
  strategyVersion: string | null
  /** The raw persisted identifier, for secondary display only. Null for legacy. */
  raw: string | null
  /** True when the identifier was present but is not one this UI can name. */
  unknown: boolean
}

/**
 * Resolve a run's `query_strategy_version` to something a reader can act on.
 *
 * Never throws and never guesses: an unrecognised value is `unknown`, so the UI
 * can say "we do not know this strategy" and still show the raw text, instead
 * of silently claiming the run was a legacy single-pass.
 */
export function resolveDiscoveryView(
  identifier: string | null | undefined,
): ResolvedDiscoveryView {
  const raw = (identifier ?? '').trim()
  if (!raw || raw === LEGACY_ALIAS) {
    return {
      view: null,
      labelKey: LEGACY_DISCOVERY_LABEL_KEY,
      strategyVersion: null,
      raw: null,
      unknown: false,
    }
  }

  const at = raw.indexOf(SEPARATOR)
  const strategyVersion = at === -1 ? null : raw.slice(0, at)
  const view = at === -1 ? null : raw.slice(at + 1)
  const labelKey = view ? DISCOVERY_VIEW_LABEL_KEYS[view] : undefined

  if (strategyVersion === G4_STRATEGY_VERSION && labelKey) {
    return { view, labelKey, strategyVersion, raw, unknown: false }
  }

  // Present, but not ours to name — a future strategy, a foreign one, or a
  // malformed value. The raw identifier travels with it so the reader can see
  // exactly what the run recorded.
  return { view: null, labelKey: UNKNOWN_DISCOVERY_LABEL_KEY, strategyVersion, raw, unknown: true }
}
