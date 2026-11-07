"""Extend gas volume and cost statistics from pgnig-sensor's billing readings.

pgnig-sensor only learns a meter reading (and its invoice) once per billing
period, so a plain total_increasing sensor drops two months of gas onto the day
the reading shows up. Here every new reading is spread evenly over the hours of
the period it covers: from the day after our statistic's last point up to and
including the reading date. The matching invoice's gross amount is spread the
same way, so cost reflects the real bill rather than a guessed unit price.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    get_metadata,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_INVOICE_AMOUNT,
    ATTR_INVOICE_NUMBER,
    ATTR_INVOICE_WEAR,
    ATTR_READING_DATE,
    ATTR_WEAR,
    COST_KEY,
    COST_UID_PREFIX,
    CURRENCY,
    DOMAIN,
    METER_UID_PREFIX,
    SOURCE_PLATFORM,
    VOLUME_KEY,
    VOLUME_UNIT,
)
from .spread import HOUR, hourly_points

_LOGGER = logging.getLogger(__name__)

# Invoice and reading volumes are both whole m³; allow for float noise.
WEAR_TOLERANCE = 0.01


def discover_meters(hass: HomeAssistant) -> list[str]:
    """Meter numbers of the enabled pgnig-sensor gas meters."""
    meters = []
    for entry in er.async_get(hass).entities.values():
        if entry.platform != SOURCE_PLATFORM or entry.disabled_by is not None:
            continue
        if entry.unique_id.startswith(METER_UID_PREFIX):
            meters.append(entry.unique_id[len(METER_UID_PREFIX) :].split("_")[0])
    return sorted(set(meters))


def entity_for(hass: HomeAssistant, prefix: str, meter: str) -> str | None:
    for entry in er.async_get(hass).entities.values():
        if entry.platform == SOURCE_PLATFORM and entry.unique_id.startswith(
            f"{prefix}{meter}_"
        ):
            return entry.entity_id
    return None


def _to_dt(start) -> datetime:
    """Recorder 'start' may be a float timestamp or a datetime; normalise to UTC."""
    if isinstance(start, (int, float)):
        return dt_util.utc_from_timestamp(start)
    return dt_util.as_utc(start)


def _local_midnight(day: date) -> datetime:
    return dt_util.as_utc(dt_util.start_of_local_day(day))


def _reading_day(value) -> date | None:
    """pgnig-sensor gives the reading date as UTC midnight; read it as a local day."""
    if not value:
        return None
    parsed = dt_util.parse_datetime(str(value))
    if parsed is None:
        return None
    return dt_util.as_local(parsed).date()


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _last_point(hass: HomeAssistant, statistic_id: str) -> tuple[datetime | None, float]:
    """(last point start, cumulative sum) of a statistic, or (None, 0)."""
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, {"sum"}
    )
    rows = last.get(statistic_id)
    if not rows:
        return None, 0.0
    return _to_dt(rows[0]["start"]), float(rows[0].get("sum") or 0.0)


async def _write(
    hass: HomeAssistant,
    statistic_id: str,
    default_name: str,
    unit: str,
    unit_class: str | None,
    points: list[tuple[datetime, float, float]],
) -> None:
    instance = get_instance(hass)
    existing = await instance.async_add_executor_job(
        lambda: get_metadata(hass, statistic_ids={statistic_id})
    )
    name = existing[statistic_id][1].get("name") if statistic_id in existing else None
    metadata = StatisticMetaData(
        mean_type=StatisticMeanType.NONE,
        has_sum=True,
        name=name or default_name,
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=unit,
        unit_class=unit_class,
    )
    async_add_external_statistics(
        hass,
        metadata,
        [StatisticData(start=s, state=c, sum=total) for s, c, total in points],
    )
    # Let the recorder commit before anyone reads the last point again.
    await instance.async_block_till_done()


async def _extend(
    hass: HomeAssistant,
    statistic_id: str,
    default_name: str,
    unit: str,
    unit_class: str | None,
    reading_day: date,
    total: float,
) -> bool:
    """Spread `total` over the days after the statistic's last point up to `reading_day`."""
    period_end = _local_midnight(reading_day + timedelta(days=1))
    last_start, last_sum = await _last_point(hass, statistic_id)

    if last_start is None:
        # Nothing to measure the period from: anchor a zero point at the
        # reading so the next period can be spread correctly.
        points = [(period_end - HOUR, 0.0, 0.0)]
        _LOGGER.info("%s: no history yet, anchored at %s", statistic_id, reading_day)
    else:
        last_day = dt_util.as_local(last_start).date()
        period_start = _local_midnight(last_day + timedelta(days=1))
        if period_start >= period_end:
            return False
        points = hourly_points(period_start, period_end, total, last_sum)
        _LOGGER.info(
            "%s: spread %.2f %s over %s – %s (%d h)",
            statistic_id,
            total,
            unit,
            last_day + timedelta(days=1),
            reading_day,
            len(points),
        )

    await _write(hass, statistic_id, default_name, unit, unit_class, points)
    return True


async def async_sync(hass: HomeAssistant, meter: str) -> None:
    """Bring both statistics up to the latest reading and its invoice."""
    meter_entity = entity_for(hass, METER_UID_PREFIX, meter)
    state = hass.states.get(meter_entity) if meter_entity else None
    if state is None:
        _LOGGER.debug("Meter %s: pgnig-sensor entity not available yet", meter)
        return

    reading_day = _reading_day(state.attributes.get(ATTR_READING_DATE))
    wear = _float(state.attributes.get(ATTR_WEAR))
    if reading_day is None or wear is None or wear < 0:
        _LOGGER.debug("Meter %s: no usable reading in %s", meter, state.attributes)
        return

    await _extend(
        hass,
        f"{DOMAIN}:{VOLUME_KEY.format(meter=meter)}",
        f"Gaz {meter}",
        VOLUME_UNIT,
        "volume",
        reading_day,
        wear,
    )

    cost_entity = entity_for(hass, COST_UID_PREFIX, meter)
    cost_state = hass.states.get(cost_entity) if cost_entity else None
    if cost_state is None:
        return
    amount = _float(cost_state.attributes.get(ATTR_INVOICE_AMOUNT))
    invoice_wear = _float(cost_state.attributes.get(ATTR_INVOICE_WEAR))
    if amount is None or invoice_wear is None:
        return
    if abs(invoice_wear - wear) > WEAR_TOLERANCE:
        # The invoice for this reading has not arrived yet (or is a forecast
        # invoice); wait for the one whose volume matches the reading.
        _LOGGER.debug(
            "Meter %s: invoice %s (%s m³) does not match reading of %s m³ yet",
            meter,
            cost_state.attributes.get(ATTR_INVOICE_NUMBER),
            invoice_wear,
            wear,
        )
        return

    await _extend(
        hass,
        f"{DOMAIN}:{COST_KEY.format(meter=meter)}",
        f"Gaz {meter} — koszt",
        CURRENCY,
        None,
        reading_day,
        amount,
    )
