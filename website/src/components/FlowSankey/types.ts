/**
 * The data the chart is handed, as `tools/snapshot.py` publishes it.
 *
 * Every number in a case file is an *exact rational string* — "400", "-600",
 * "8/15" — never a JSON float: the values are the engine's published
 * specification and have to stay checkable by hand. `null` is the engine
 * publishing nothing at all, usually because a reading it needs is
 * unavailable.
 */

/** An exact rational, as stored. */
export type Rat = string | null;

/** A published value: a scalar, or a (possibly nested) map of them. */
export type ValueTree = Rat | {[key: string]: ValueTree};

export type AdapterKind = 'grid' | 'pv' | 'battery' | 'consumer';

/** The unmetered home base load is not an adapter, but it is drawn like one. */
export type DeviceKind = AdapterKind | 'home';

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

export interface Result {
  property: string;
  value: ValueTree;
}

export interface CaseState {
  id: string;
  note: string;
  /** Set when the engine's answer here is an unresolved modelling choice. */
  open_question?: string;
  readings: {[uid: string]: Rat};
  price: Rat;
  /** Every catalogued property, as the engine computed it. */
  results: Result[];
}

export interface ReferenceCase {
  id: string;
  title: string;
  summary: string;
  shows: string[];
  topology: Adapter[];
  states: CaseState[];
}

export type Unit = 'W' | 'share' | 'ratio' | 'EUR/h' | 'EUR/kWh';

/** One entry of `docs/spec/properties.json`. */
export interface PropertyDoc {
  title: string;
  unit: Unit;
  layer: number;
  definition: string;
  formula?: string;
  keys?: string | string[];
  note?: string;
}

export interface PropertyCatalog {
  layers?: {[id: string]: string};
  properties: {[name: string]: PropertyDoc};
}

/** One Home Assistant sensor, from `docs/spec/cases/sensors.json`. */
export interface SensorDoc {
  /** The device it sits on: `combined` is the whole-home device. */
  device: 'combined' | DeviceKind;
  key: string | null;
  translation_key: string;
  /** Display name; a per-source sensor carries a `{source}` placeholder. */
  name: string;
  /** The engine property its value reads. */
  property: string | null;
  /** How that property is indexed: by the sensor's device, by device and source, or not. */
  index: 'device' | 'device_source' | null;
  /** A `Total …` sensor: accumulates over time, so no snapshot shows it. */
  accumulates: boolean;
}

export interface SensorMap {
  sensors: SensorDoc[];
}

/** The four channels gross power splits into. */
export type Channel = 'export' | 'consumption' | 'charging' | 'standby';
