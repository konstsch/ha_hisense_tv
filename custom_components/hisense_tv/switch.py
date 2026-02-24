"""Hisense TV switch entity"""
import logging

import wakeonlan

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.const import CONF_IP_ADDRESS, CONF_MAC, CONF_NAME

from .const import CONF_MQTT_CLIENT_ID, DEFAULT_CLIENT_ID, DEFAULT_NAME, DOMAIN
from .helper import HisenseTvBase

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Start HisenseTV switch setup process."""
    _LOGGER.debug("async_setup_entry config: %s", config_entry.data)

    domain_data = hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {})
    mqtt_client = domain_data.get("mqtt_client")
    if not mqtt_client:
        _LOGGER.error("MQTT client not available")
        return

    name = config_entry.data[CONF_NAME]
    mac = config_entry.data[CONF_MAC]
    ip_address = config_entry.data.get(CONF_IP_ADDRESS, wakeonlan.BROADCAST_IP)
    client_id = config_entry.data.get(CONF_MQTT_CLIENT_ID, DEFAULT_CLIENT_ID)
    uid = config_entry.unique_id
    if uid is None:
        uid = config_entry.entry_id

    entity = HisenseTvSwitch(
        hass=hass,
        name=name,
        mac=mac,
        uid=uid,
        ip_address=ip_address,
        mqtt_client=mqtt_client,
        client_id=client_id,
    )
    async_add_entities([entity])


class HisenseTvSwitch(SwitchEntity, HisenseTvBase):
    """Hisense TV switch entity."""

    def __init__(self, hass, name, mac, uid, ip_address, mqtt_client, client_id=DEFAULT_CLIENT_ID):
        HisenseTvBase.__init__(
            self=self,
            hass=hass,
            name=name,
            mac=mac,
            uid=uid,
            ip_address=ip_address,
            mqtt_client=mqtt_client,
            client_id=client_id,
        )
        self._is_on = False

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        wakeonlan.send_magic_packet(self._mac, ip_address=self._ip_address)

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        await self._mqtt_client.async_publish(
            topic=self._out_topic("/remoteapp/tv/remote_service/%s/actions/sendkey"),
            payload="KEY_POWER",
            retain=False,
        )

    @property
    def is_on(self):
        return self._is_on

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._unique_id)},
            "name": self._name,
            "manufacturer": DEFAULT_NAME,
        }

    @property
    def unique_id(self):
        """Return the unique id of the entity."""
        return f"{self._unique_id}_switch"

    @property
    def name(self):
        return self._name

    @property
    def icon(self):
        return self._icon

    @property
    def device_class(self):
        _LOGGER.debug("device_class")
        return SwitchDeviceClass.SWITCH

    @property
    def should_poll(self):
        """Enable polling to request state periodically."""
        return True

    async def async_will_remove_from_hass(self):
        for unsubscribe in list(self._subscriptions.values()):
            unsubscribe()

    async def _request_state(self):
        """Request TV state via MQTT (gettvstate and sourcelist)."""
        await self._mqtt_client.async_publish(
            topic=self._out_topic("/remoteapp/tv/ui_service/%s/actions/gettvstate"),
            payload="",
            retain=False,
        )
        await self._mqtt_client.async_publish(
            topic=self._out_topic("/remoteapp/tv/ui_service/%s/actions/sourcelist"),
            payload="",
            retain=False,
        )

    async def async_update(self):
        """Poll TV state periodically."""
        await self._request_state()

    async def async_added_to_hass(self):
        self._subscriptions["tvsleep"] = await self._mqtt_client.async_subscribe(
            topic=self._in_topic(
                "/remoteapp/mobile/broadcast/platform_service/actions/tvsleep"
            ),
            callback=self._message_received_turnoff,
        )

        self._subscriptions["state"] = await self._mqtt_client.async_subscribe(
            topic=self._in_topic("/remoteapp/mobile/broadcast/ui_service/state"),
            callback=self._message_received_state,
        )

        self._subscriptions["volume"] = await self._mqtt_client.async_subscribe(
            topic=self._in_topic(
                "/remoteapp/mobile/broadcast/platform_service/actions/volumechange"
            ),
            callback=self._message_received_state,
        )

        self._subscriptions["sourcelist"] = await self._mqtt_client.async_subscribe(
            topic=self._out_topic("/remoteapp/mobile/%s/ui_service/data/sourcelist"),
            callback=self._message_received_state,
        )

        # Request initial state on startup
        await self._request_state()

    async def _message_received_turnoff(self, msg):
        _LOGGER.debug("message_received_turnoff")
        self._is_on = False
        self.async_write_ha_state()

    async def _message_received_state(self, msg):
        if msg.retain:
            _LOGGER.debug("SWITCH message_received_state - skip retained message")
            return

        _LOGGER.debug("SWITCH message_received_state - turn on")
        self._is_on = True
        self.async_write_ha_state()
