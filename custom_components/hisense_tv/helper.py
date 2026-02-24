"""Hisense TV integration helper methods."""
import asyncio
import logging

from homeassistant.const import MAJOR_VERSION, MINOR_VERSION

from .const import DEFAULT_CLIENT_ID

_LOGGER = logging.getLogger(__name__)


async def mqtt_pub_sub(mqtt_client, pub, sub, payload=""):
    """Wrapper for publishing MQTT topics and receive replies on a subscribed topic."""
    queue = asyncio.Queue()

    def put(msg):
        queue.put_nowait((msg,))

    async def get():
        while True:
            yield await asyncio.wait_for(queue.get(), timeout=10)

    unsubscribe = await mqtt_client.async_subscribe(topic=sub, callback=put)
    await mqtt_client.async_publish(topic=pub, payload=payload)
    return get(), unsubscribe


class HisenseTvBase(object):
    """Hisense TV base entity."""

    def __init__(
        self,
        hass,
        name: str,
        mac: str,
        uid: str,
        ip_address: str,
        mqtt_client,
        client_id: str = DEFAULT_CLIENT_ID,
    ):
        self._client = client_id
        self._hass = hass
        self._mqtt_client = mqtt_client
        self._name = name
        self._mac = mac
        self._ip_address = ip_address
        self._unique_id = uid
        self._icon = (
            "mdi:television-clean"
            if MAJOR_VERSION <= 2021 and MINOR_VERSION < 11
            else "mdi:television-shimmer"
        )
        self._subscriptions = {
            "tvsleep": lambda: None,
            "state": lambda: None,
            "volume": lambda: None,
            "sourcelist": lambda: None,
        }

    def _out_topic(self, topic=""):
        try:
            out_topic = topic % self._client
        except Exception:
            out_topic = topic % self._client
        _LOGGER.debug("_out_topic: %s", out_topic)
        return out_topic

    def _in_topic(self, topic=""):
        try:
            in_topic = topic % self._client
        except Exception:
            in_topic = topic
        _LOGGER.debug("_in_topic: %s", in_topic)
        return in_topic
