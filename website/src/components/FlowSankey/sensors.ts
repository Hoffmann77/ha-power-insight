/**
 * Which Home Assistant sensor shows each value the Sankey draws.
 *
 * PROTOTYPE: hand-copied from `sensor.py` and `strings.json`. The production
 * version should have `tools/snapshot.py` export this mapping next to the
 * property catalog, so a sensor added or renamed in the integration shows up
 * here and a test can fail when a sensor has no place on the diagram.
 */
import type {AdapterKind} from '../CaseDiagram/types';

export type Channel = 'export' | 'consumption' | 'charging' | 'standby';

export const CHANNELS: Channel[] = ['export', 'consumption', 'charging', 'standby'];

export const CHANNEL_TITLE: {[k in Channel]: string} = {
  export: 'Grid export',
  consumption: 'Home consumption',
  charging: 'Battery charging',
  standby: 'System standby',
};

/** The noun a per-source channel sensor ends in: "Production to <noun>". */
const CHANNEL_NOUN: {[k in Channel]: string} = {
  export: 'grid',
  consumption: 'home consumption',
  charging: 'batteries',
  standby: 'system standby',
};

/** How each device kind's per-source channel sensors start. */
const SOURCE_VERB: {[k in AdapterKind]?: string} = {
  grid: 'Import to',
  pv: 'Production to',
  battery: 'Discharge to',
};

export interface SensorRef {
  /** The entity name as HA shows it, after the device name. */
  sensor: string;
  /** The engine property the sensor reads. */
  property: string;
  /** Key into a per-device map; absent for a scalar property. */
  key?: string;
}

/**
 * The three sensors for one source → channel link: its watts, the fraction of
 * the source's output it is (ratio), and the fraction of the channel it
 * supplies (share). Null where the device has no such sensor — the grid never
 * exports to itself.
 */
export function linkSensors(
  kind: AdapterKind,
  uid: string,
  channel: Channel,
): {power: SensorRef; ratio: SensorRef; share: SensorRef} | null {
  const verb = SOURCE_VERB[kind];
  if (!verb || (kind === 'grid' && channel === 'export')) {
    return null;
  }
  const base = `${verb} ${CHANNEL_NOUN[channel]}`;
  const shareName =
    channel === 'export'
      ? 'Share of grid export'
      : channel === 'consumption'
        ? 'Share of home consumption'
        : channel === 'charging'
          ? 'Share of battery charging'
          : 'Share of system standby';
  return {
    power: {sensor: base, property: `source_adapters_${channel}_power`, key: uid},
    ratio: {sensor: `${base} ratio`, property: `source_adapters_${channel}_ratios`, key: uid},
    share: {sensor: shareName, property: `source_adapters_${channel}_shares`, key: uid},
  };
}

/** A channel's whole-home sensors. */
export const CHANNEL_SENSORS: {[k in Channel]: SensorRef[]} = {
  export: [
    {sensor: 'Export power (grid)', property: 'combined_grid_export'},
    {sensor: 'Export ratio', property: 'gross_power_export_ratio'},
    {sensor: 'Levelized export cost rate', property: 'combined_levelized_export_cost_rate'},
    {sensor: 'Export compensation rate (grid)', property: 'combined_export_compensation_rate'},
  ],
  consumption: [
    {sensor: 'Home consumption power', property: 'combined_consumption'},
    {sensor: 'Home consumption ratio', property: 'gross_power_consumption_ratio'},
    {sensor: 'Consumption cost rate', property: 'combined_consumption_cost_rate'},
    {
      sensor: 'Levelized consumption cost rate',
      property: 'combined_levelized_consumption_cost_rate',
    },
  ],
  charging: [
    {sensor: 'Battery charging power', property: 'combined_charging_power'},
    {sensor: 'Battery charging ratio', property: 'gross_power_charging_ratio'},
    {sensor: 'Charging cost rate', property: 'combined_charging_cost_rate'},
    {sensor: 'Levelized charging cost rate', property: 'combined_lcoo_rate_corrected'},
  ],
  standby: [
    {sensor: 'System standby power', property: 'combined_standby_power'},
    {sensor: 'System standby ratio', property: 'gross_power_standby_ratio'},
    {
      sensor: 'Levelized system standby cost rate',
      property: 'combined_levelized_standby_cost_rate',
    },
  ],
};

/** The money a source earns or costs, per device. */
export function sourceMoneySensors(kind: AdapterKind, uid: string): SensorRef[] {
  if (kind === 'grid') {
    return [{sensor: 'Import cost rate', property: 'source_adapters_coe_rate', key: uid}];
  }
  return [
    {sensor: 'Cost savings rate', property: 'adapters_saving_rates', key: uid},
    {
      sensor: 'Export compensation rate',
      property: 'source_adapters_export_compensation_rates',
      key: uid,
    },
    {sensor: 'Financial return rate', property: 'adapters_financial_return_rates', key: uid},
  ];
}

/** What a sink costs to run, or saves, per device. */
export function sinkMoneySensors(kind: AdapterKind | 'home', uid: string): SensorRef[] {
  switch (kind) {
    case 'home':
      return [
        {sensor: 'Power (home base load)', property: 'home_base_load_power'},
        {sensor: 'Avoided cost rate', property: 'home_base_load_avoided_cost_rate'},
      ];
    case 'consumer':
      return [
        {sensor: 'Consumption share', property: 'sink_adapters_consumption_shares', key: uid},
        {sensor: 'Operating cost rate', property: 'sink_adapters_coo_rates', key: uid},
        {
          sensor: 'Levelized operating cost rate',
          property: 'sink_adapters_lcoo_rates',
          key: uid,
        },
        {sensor: 'Avoided cost rate', property: 'sink_adapters_avoided_cost_rates', key: uid},
      ];
    case 'grid':
      return [
        {sensor: 'Export power', property: 'combined_grid_export'},
        {sensor: 'Export compensation rate', property: 'combined_export_compensation_rate'},
      ];
    default:
      return [
        {sensor: 'Operating cost rate', property: 'source_adapters_coo_rates', key: uid},
        {
          sensor: 'Levelized operating cost rate',
          property: 'source_adapters_lcoo_rates_corrected',
          key: uid,
        },
      ];
  }
}

/** The one euro figure a node is labelled with in the money view. */
export function headlineMoney(
  side: 'source' | 'sink',
  kind: AdapterKind | 'home',
  uid: string,
): SensorRef {
  if (side === 'source') {
    return kind === 'grid'
      ? {sensor: 'Import cost rate', property: 'source_adapters_coe_rate', key: uid}
      : {sensor: 'Financial return rate', property: 'adapters_financial_return_rates', key: uid};
  }
  switch (kind) {
    case 'home':
      return {sensor: 'Avoided cost rate', property: 'home_base_load_avoided_cost_rate'};
    case 'consumer':
      return {
        sensor: 'Levelized operating cost rate',
        property: 'sink_adapters_lcoo_rates',
        key: uid,
      };
    case 'grid':
      return {sensor: 'Export compensation rate', property: 'combined_export_compensation_rate'};
    default:
      return {
        sensor: 'Levelized operating cost rate',
        property: 'source_adapters_lcoo_rates_corrected',
        key: uid,
      };
  }
}

/** The headline euro figure for a channel. */
export const CHANNEL_MONEY: {[k in Channel]: SensorRef} = {
  export: {sensor: 'Levelized export cost rate', property: 'combined_levelized_export_cost_rate'},
  consumption: {
    sensor: 'Levelized consumption cost rate',
    property: 'combined_levelized_consumption_cost_rate',
  },
  charging: {sensor: 'Levelized charging cost rate', property: 'combined_lcoo_rate_corrected'},
  standby: {
    sensor: 'Levelized system standby cost rate',
    property: 'combined_levelized_standby_cost_rate',
  },
};
