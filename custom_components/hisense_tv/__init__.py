"""Component init"""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant

from .const import (
    CONF_MQTT_CLIENT_ID,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_PORT,
    CONF_MQTT_USERNAME,
    DEFAULT_CLIENT_ID,
    DEFAULT_MQTT_PASSWORD,
    DEFAULT_MQTT_PORT,
    DEFAULT_MQTT_USERNAME,
    DOMAIN,
)
from .mqtt_client import HisenseMqttClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["media_player", "switch", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up HisenseTV from a config entry."""
    _LOGGER.debug("async_setup_entry")

    if not await async_migrate_entry(hass, entry):
        return False

    data = entry.data
    ip_address = data.get(CONF_IP_ADDRESS)
    if not ip_address:
        _LOGGER.error("IP address is required for direct MQTT connection")
        return False

    mqtt_client = HisenseMqttClient(
        hass=hass,
        host=ip_address,
        port=data.get(CONF_MQTT_PORT, DEFAULT_MQTT_PORT),
        username=data.get(CONF_MQTT_USERNAME, DEFAULT_MQTT_USERNAME),
        password=data.get(CONF_MQTT_PASSWORD, DEFAULT_MQTT_PASSWORD),
        client_id=data.get(CONF_MQTT_CLIENT_ID, DEFAULT_CLIENT_ID),
    )
    if not await mqtt_client.async_connect():
        _LOGGER.error("Failed to connect to TV MQTT broker")
        return False

    hass.data[DOMAIN][entry.entry_id] = {"mqtt_client": mqtt_client}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass, entry):
    """Unload HisenseTV config entry."""
    _LOGGER.debug("async_unload_entry")
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        domain_data = hass.data[DOMAIN].pop(entry.entry_id, {})
        mqtt_client = domain_data.get("mqtt_client")
        if mqtt_client:
            mqtt_client.disconnect()
    return unload_ok


async def async_setup(hass, config):
    """Set up the HisenseTV integration."""
    _LOGGER.debug("async_setup")
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_migrate_entry(hass, entry: ConfigEntry) -> bool:
    """Migrate config entry from v1 to v2 (add MQTT credentials)."""
    if entry.version >= 2:
        return True

    data = dict(entry.data)
    data.setdefault(CONF_MQTT_PORT, DEFAULT_MQTT_PORT)
    data.setdefault(CONF_MQTT_USERNAME, DEFAULT_MQTT_USERNAME)
    data.setdefault(CONF_MQTT_PASSWORD, DEFAULT_MQTT_PASSWORD)
    data.setdefault(CONF_MQTT_CLIENT_ID, DEFAULT_CLIENT_ID)

    hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True
