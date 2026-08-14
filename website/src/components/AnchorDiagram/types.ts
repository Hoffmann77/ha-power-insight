/**
 * The anchor-case JSON contract (see docs/spec/anchor-case.schema.json).
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

export interface DerivationStep {
  text: string;
  detail?: string;
  math?: string;
  result?: string;
}

export interface Certification {
  status: 'verified' | 'unverified';
  by?: string;
  date?: string;
  method?: string;
  engine_commit?: string;
}

export interface Expectation {
  property: string;
  value: ValueTree;
  derivation: DerivationStep[];
  certification: Certification;
}

export interface AnchorState {
  id: string;
  note: string;
  /** Set when the engine's answer here is an unresolved modelling choice. */
  open_question?: string;
  readings: {[uid: string]: Rat};
  price: Rat;
  expectations: Expectation[];
}

export interface AnchorCase {
  id: string;
  title: string;
  summary: string;
  /** The modelling choices this case pins down. */
  decides: string[];
  topology: Adapter[];
  states: AnchorState[];
}

/** Which value family the diagram is currently labelled with. */
export type Metric = 'power' | 'shares' | 'cost';

/** A node's role this snapshot, derived from the sign of its reading. */
export type Role = 'source' | 'sink' | 'idle';
