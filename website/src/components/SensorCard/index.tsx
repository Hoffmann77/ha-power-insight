import React, {type ReactNode} from 'react';
import styles from './styles.module.css';

// One card per sensor *family*: a plain-language explanation plus the list of
// entities it covers, each with its unit and the option that creates it.
//
//   <SensorCard title="Operating cost" sensors={[
//     {name: 'Operating cost rate', unit: 'EUR/h', on: 'Cost method: Standard'},
//     {name: 'Total operating cost', unit: 'EUR', on: 'Total costs'},
//   ]} requires="Exports to the grid">
//     What running the system costs …
//   </SensorCard>

export type Sensor = {
  /** Entity name as it appears in Home Assistant (after the device name). */
  name: string;
  /** Unit of measurement. `EUR` stands for your Home Assistant currency. */
  unit: string;
  /** The option that creates it ("Power split (W)", "Cost method: Levelized"). */
  on: string;
};

export function SensorCard({
  title,
  sensors,
  requires,
  diagnostic = false,
  children,
}: {
  title: string;
  sensors: Sensor[];
  /** A device setting the sensors also need, e.g. "Exports to the grid". */
  requires?: string;
  diagnostic?: boolean;
  children?: ReactNode;
}) {
  return (
    <section className={styles.card}>
      <header className={styles.header}>
        <h4 className={styles.title}>{title}</h4>
        {diagnostic && <span className={styles.flag}>Diagnostic</span>}
      </header>
      {children && <div className={styles.body}>{children}</div>}
      <table className={styles.sensors}>
        <thead>
          <tr>
            <th>Sensor</th>
            <th>Unit</th>
            <th>Turn on with</th>
          </tr>
        </thead>
        <tbody>
          {sensors.map((s) => (
            <tr key={s.name}>
              <td className={styles.name}>{s.name}</td>
              <td>
                <span className={styles.unit}>{s.unit}</span>
              </td>
              <td className={styles.option}>{s.on}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {requires && (
        <p className={styles.requires}>
          <span aria-hidden="true">⚙︎</span> Only when <strong>{requires}</strong>.
        </p>
      )}
    </section>
  );
}

/** Stacks cards with consistent spacing. */
export function SensorCards({children}: {children: ReactNode}) {
  return <div className={styles.stack}>{children}</div>;
}
