"""Constants for the PGNiG/ORLEN gas history integration."""
from __future__ import annotations

DOMAIN = "pgnig_gas"

# The pgnig-sensor integration (pawelhulek/pgnig-sensor) whose entities we read.
SOURCE_PLATFORM = "pgnig_gas_sensor"
# Its entity unique_ids are "<prefix><meter number>_<PP id>".
METER_UID_PREFIX = "pgnig_sensor"
COST_UID_PREFIX = "pgnig_cost_tracking_sensor"

CONF_METER = "meter"

VOLUME_KEY = "history_{meter}"
COST_KEY = "cost_history_{meter}"
VOLUME_UNIT = "m³"
CURRENCY = "PLN"

# Attributes published by pgnig-sensor.
ATTR_WEAR = "wear"
ATTR_READING_DATE = "reading_date"
ATTR_INVOICE_NUMBER = "last_invoice_number"
ATTR_INVOICE_AMOUNT = "last_invoice_gross_amount"
ATTR_INVOICE_WEAR = "last_invoice_wear_m3"

SERVICE_SYNC = "sync"
