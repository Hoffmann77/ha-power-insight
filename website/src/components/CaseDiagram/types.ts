/**
 * The reference-case JSON contract, as published by `tools/export_cases.py`
 * from the Python cases in `tests/engine/reference/`.
 *
 * Every number in a case file is an *exact rational string* — "400", "-600",
 * "8/15", "3/20" — never a JSON float. That is the whole point of the format:
 * these values are the engine's published specification and have to stay
 * comparable by hand.
 */

/** An exact rational, as stored. `null` models an unavailable reading. */
export type Rat = string | null;

/** A stored expectation value: a scalar, or a (possibly nested) map of them. */
export type ValueTree = Rat | {[key: string]: ValueTree};

export type AdapterKind = 'grid' | 'pv' | 'battery' | 'consumer';

/** The virtual home base load is not an adapter, but it is drawn like one. */
export type NodeKind = AdapterKind | 'home';

export interface AdapterConfig {
  has_price_entity?: boolean;
  lcoe?: Rat;
  lcos?: Rat;
  lco2_intensity?: Rat;
  exports_power?: boolean;
  export_compensation?: Rat;
  correction_factor?: Rat;
  charge_from_adapters?: string[];
  power_from_adapters?: string[];
}

export interface Adapter {
  uid: string;
  kind: AdapterKind;
  config: AdapterConfig;
}

export interface Expectation {
  property: string;
  value: ValueTree;
  /**
   * Whether somebody has derived this slot — and the only thing that says so.
   *
   * Expectation values are literal, so a derived answer of "there is no value
   * here" is a plain `null` and is indistinguishable from an empty slot by its
   * value alone. Read this flag, never the value, to decide which you have.
   *
   * `false` is the default and, for now, most of the corpus.
   */
  derived: boolean;
}

export interface CaseState {
  id: string;
  note: string;
  /** Set when the engine's answer here is an unresolved modelling choice. */
  open_question?: string;
  readings: {[uid: string]: Rat};
  price: Rat;
  expectations: Expectation[];
}

export interface ReferenceCase {
  id: string;
  title: string;
  summary: string;
  /** The modelling choices this case pins down. */
  decides: string[];
  topology: Adapter[];
  states: CaseState[];
}

/**
 * The property catalog (`docs/spec/properties.json`): what each published
 * property means, what unit it is in, and which layer of the engine it belongs
 * to. Passed in as a prop for the same reason the cases are — it is versioned
 * documentation, and an old docs version must keep rendering its own copy.
 */
export interface PropertyDoc {
  title: string;
  unit: Unit;
  layer: number;
  definition: string;
  formula?: string;
  depends_on?: string[];
  answer_shape?: string;
  derivation_steps?: string[];
  note?: string;
}

export interface PropertyCatalog {
  layers?: {[id: string]: string};
  properties: {[name: string]: PropertyDoc};
}

/** The units the catalog quotes. Drives how a value is rendered. */
export type Unit = 'W' | 'share' | 'ratio' | 'EUR/h' | 'EUR/kWh';

/**
 * Which layer of the engine the diagram is currently showing. These are the
 * catalog's own layers, so the tab row and the property table always agree
 * about what belongs where.
 */
export type LayerId = '1' | '2' | '3' | '4';

/** A node's role this snapshot, derived from the sign of its reading. */
export type Role = 'source' | 'sink' | 'idle';

/** Which channel of the gross-power split a sink belongs to. */
export type Channel = 'export' | 'charging' | 'consumption' | 'standby';

/**
 * The generated coverage table (`docs/spec/cases/coverage.json`): which rungs
 * of the ladder each property is actually settled by, and which modelling
 * decision each case carries.
 *
 * `settledBy` is the load-bearing field, and it is deliberately not a count of
 * appearances. Almost every property has *some* value on the first rung, so
 * "where does it first appear" says nothing; the rungs listed here are the
 * ones that each published a value no earlier rung had.
 */
export interface PropertyCoverage {
  title: string;
  layer: number;
  /** Slots this property has across the corpus — one per snapshot. */
  slots: number;
  /** Slots a human has filled in. */
  derived: number;
  /** Cases where at least one slot has been derived. */
  derived_in: string[];
}

export interface CaseCoverage {
  case: string;
  case_title: string;
  decides: string[];
  slots: number;
  derived: number;
}

export interface Coverage {
  /** Case ids in ladder order. */
  order: string[];
  decisions: CaseCoverage[];
  properties: {[name: string]: PropertyCoverage};
  totals: {
    slots: number;
    derived: number;
    /** Properties with no derived value anywhere yet. */
    untouched: string[];
  };
}
