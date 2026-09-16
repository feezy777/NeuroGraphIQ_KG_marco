/**
 * Discovery View resolution — the ONE rule that turns a persisted strategy
 * identifier into something a reader can act on.
 *
 * The fixtures are the real persisted values: CA3's Pass A run genuinely stored
 * `G4HR1/NAMED_CLASSIC_CIRCUITS`, and Left Hippocampus's legacy run genuinely
 * stored null. The rest pin the boundaries — silence is legacy, an unknown
 * strategy is unknown, and neither is ever shown as one of the four views.
 */
import { describe, expect, it } from 'vitest'
import {
  G4_DISCOVERY_VIEWS,
  G4_STRATEGY_VERSION,
  LEGACY_DISCOVERY_LABEL_KEY,
  UNKNOWN_DISCOVERY_LABEL_KEY,
  resolveDiscoveryView,
} from './discoveryView'

/** The label a caller would render, in the default language. */
const label = (id: string | null | undefined) => resolveDiscoveryView(id).labelKey

describe('the four G4 views resolve to their own label', () => {
  it.each([
    ['NAMED_CLASSIC_CIRCUITS', 'knowledgeProduction.discoveryView.namedClassic'],
    ['LOCAL_INTRINSIC_CIRCUITS', 'knowledgeProduction.discoveryView.localIntrinsic'],
    ['AFFERENT_CIRCUITS', 'knowledgeProduction.discoveryView.afferent'],
    ['EFFERENT_CIRCUITS', 'knowledgeProduction.discoveryView.efferent'],
  ])('G4HR1/%s -> %s', (view, expected) => {
    const r = resolveDiscoveryView(`${G4_STRATEGY_VERSION}/${view}`)
    expect(r.labelKey).toBe(expected)
    expect(r.view).toBe(view)
    expect(r.strategyVersion).toBe('G4HR1')
    expect(r.unknown).toBe(false)
    // The raw identifier travels WITH the resolution, so a caller can offer it
    // as secondary information without re-parsing the string.
    expect(r.raw).toBe(`G4HR1/${view}`)
  })

  it('covers exactly the four frozen views, in pilot order', () => {
    expect(G4_DISCOVERY_VIEWS).toEqual([
      'NAMED_CLASSIC_CIRCUITS',
      'LOCAL_INTRINSIC_CIRCUITS',
      'AFFERENT_CIRCUITS',
      'EFFERENT_CIRCUITS',
    ])
    const resolved = G4_DISCOVERY_VIEWS.map(v => resolveDiscoveryView(`G4HR1/${v}`).view)
    expect(resolved).toEqual([...G4_DISCOVERY_VIEWS])
  })
})

describe('a run with no view is LEGACY, never one of the four', () => {
  it.each([[null], [undefined], [''], ['   ']])('identity %s -> general discovery', id => {
    const r = resolveDiscoveryView(id as string | null | undefined)
    expect(r.labelKey).toBe(LEGACY_DISCOVERY_LABEL_KEY)
    expect(r.view).toBeNull()
    expect(r.strategyVersion).toBeNull()
    expect(r.raw).toBeNull()
    expect(r.unknown).toBe(false)
  })

  it('the backend legacy sentinel is the same fact, not a fifth view', () => {
    const r = resolveDiscoveryView('GENERAL_DISCOVERY')
    expect(r.labelKey).toBe(LEGACY_DISCOVERY_LABEL_KEY)
    expect(r.view).toBeNull()
    expect(r.unknown).toBe(false)
  })

  it('a legacy run is never labelled as any of the four views', () => {
    const legacyKeys = G4_DISCOVERY_VIEWS.map(
      v => resolveDiscoveryView(`G4HR1/${v}`).labelKey,
    )
    expect(legacyKeys).not.toContain(label(null))
  })
})

describe('anything else is UNKNOWN — never guessed, never filed as legacy', () => {
  it.each([
    'G4HR1/NOT_A_VIEW',
    'G4HR1/',
    'OTHER_FUTURE_STRATEGY',
    'FUTURE_V2/AFFERENT_CIRCUITS',
    'BRAIN_REGION_LITERATURE_MVP_V1',
    'v1',
    'AFFERENT_CIRCUITS', // the bare view token, missing its strategy prefix
  ])('%s -> unknown, with its raw value kept', id => {
    const r = resolveDiscoveryView(id)
    expect(r.labelKey).toBe(UNKNOWN_DISCOVERY_LABEL_KEY)
    expect(r.raw).toBe(id)
    // ...and it is NOT quietly reported as legacy, which would claim the run
    // used no view when it recorded a strategy we simply cannot name.
    expect(r.labelKey).not.toBe(LEGACY_DISCOVERY_LABEL_KEY)
    expect(r.view).toBeNull()
  })

  it('a foreign strategy keeps its own version token, uninterpreted', () => {
    expect(resolveDiscoveryView('FUTURE_V2/AFFERENT_CIRCUITS').strategyVersion).toBe('FUTURE_V2')
  })

  it('a malformed value with no separator has no version to report', () => {
    const r = resolveDiscoveryView('SOMETHING_ODD')
    expect(r.strategyVersion).toBeNull()
    expect(r.raw).toBe('SOMETHING_ODD')
  })
})

describe('real persisted fixtures', () => {
  it('CA3 Pass A (run 8cd2e18a) is a named/classic run', () => {
    // Verbatim from knowledge_discovery_runs.query_strategy_version.
    const r = resolveDiscoveryView('G4HR1/NAMED_CLASSIC_CIRCUITS')
    expect(r.view).toBe('NAMED_CLASSIC_CIRCUITS')
    expect(r.strategyVersion).toBe('G4HR1')
    expect(r.unknown).toBe(false)
  })

  it('Left Hippocampus (legacy) is general discovery, with no strategy version', () => {
    const r = resolveDiscoveryView(null)
    expect(r.labelKey).toBe(LEGACY_DISCOVERY_LABEL_KEY)
    expect(r.strategyVersion).toBeNull()
    expect(r.unknown).toBe(false)
  })
})

describe('the resolver is total and never throws', () => {
  it.each([null, undefined, '', ' ', '/', 'G4HR1', '///', 'G4HR1/A/B', '\t\n'])(
    'handles %j without throwing',
    id => {
      const r = resolveDiscoveryView(id as string | null | undefined)
      expect(typeof r.labelKey).toBe('string')
      expect(r.labelKey.length).toBeGreaterThan(0)
      expect(r.view === null || typeof r.view === 'string').toBe(true)
    },
  )
})
