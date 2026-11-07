# PGNiG/ORLEN Gas History (even spread) — Home Assistant

Spreads each **gas meter reading and its invoice evenly over the billing period**
it covers, so the Energy dashboard shows gas use and cost in the months it was
actually used — not all on the day the reading arrived.

## Why this exists

The [pgnig-sensor](https://github.com/pawelhulek/pgnig-sensor) integration only
learns a reading once per billing period (typically every two months). As a
`total_increasing` sensor, two months of gas then lands on a single day, and its
cost is priced at whatever unit price the sensor showed at that moment.

This integration reads pgnig-sensor's own entities (it does **not** contact
ORLEN itself) and keeps two external statistics:

- `pgnig_gas:history_<meter>` — m³, each reading's `wear` spread evenly over every
  hour from the day after the previous period up to and including the reading date;
- `pgnig_gas:cost_history_<meter>` — PLN, the **gross invoice amount** spread over
  the same days, once an invoice with the same volume as the reading shows up.

Existing points are never rewritten; new periods are appended and the cumulative
sum continues, so history imported earlier under the same ids is kept.

## Requirements

- Home Assistant 2025.8.0+
- pgnig-sensor (`pgnig_gas_sensor`) set up with your ORLEN account.

## Setup

1. Install via HACS (custom repository, category "Integration"), restart.
2. Settings → Devices & Services → Add Integration → **PGNiG/ORLEN Gas History**,
   pick the meter.
3. In the Energy dashboard, use `pgnig_gas:history_<meter>` as the gas source with
   `pgnig_gas:cost_history_<meter>` as its cost statistic — and **remove** the
   pgnig-sensor meter sensor as a gas source, or the gas is counted twice.

The statistics are checked on startup, every 6 hours and whenever the pgnig-sensor
entities change. `pgnig_gas.sync` forces a check now.

## Notes

- With no history yet, the first reading only anchors the statistic (its period
  start is unknown); from the next reading on, every period is spread.
- A forecast invoice whose volume does not match the reading is ignored; cost
  catches up when the settling invoice arrives.
