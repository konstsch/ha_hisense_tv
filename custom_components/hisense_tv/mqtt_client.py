"""Direct MQTT client for Hisense TV broker connection."""
import asyncio
import logging
import threading
from typing import Any, Callable

import paho.mqtt.client as mqtt

from .const import (
    CONF_MQTT_CLIENT_ID,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_PORT,
    CONF_MQTT_USERNAME,
    DEFAULT_CLIENT_ID,
    DEFAULT_MQTT_PASSWORD,
    DEFAULT_MQTT_PORT,
    DEFAULT_MQTT_USERNAME,
)

_LOGGER = logging.getLogger(__name__)


class HisenseMqttClient:
    """MQTT client for direct connection to Hisense TV broker."""

    def __init__(
        self,
        hass,
        host: str,
        port: int = DEFAULT_MQTT_PORT,
        username: str = DEFAULT_MQTT_USERNAME,
        password: str = DEFAULT_MQTT_PASSWORD,
        client_id: str = DEFAULT_CLIENT_ID,
    ):
        self._hass = hass
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._client_id = client_id
        self._client: mqtt.Client | None = None
        self._connected = False
        self._subscriptions: dict[str, Callable] = {}
        self._connect_event = threading.Event()

    def _do_connect(self) -> bool:
        """Sync connect - runs in executor."""
        self._connect_event.clear()
        self._client = mqtt.Client(
            client_id=self._client_id,
            protocol=mqtt.MQTTv311,
        )
        self._client.username_pw_set(self._username, self._password)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.connect(self._host, self._port, keepalive=60)
        self._client.loop_start()
        self._connect_event.wait(timeout=10)
        return self._connected

    def connect(self) -> bool:
        """Connect to the TV MQTT broker."""
        try:
            _LOGGER.debug("Connecting to TV MQTT broker %s:%s", self._host, self._port)
            return self._do_connect()
        except Exception as ex:
            _LOGGER.error("Failed to connect to TV MQTT broker: %s", ex)
            return False

    async def async_connect(self) -> bool:
        """Async connect - runs in executor."""
        try:
            return await self._hass.async_add_executor_job(self._do_connect)
        except Exception as ex:
            _LOGGER.error("Failed to connect to TV MQTT broker: %s", ex)
            return False

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """Handle connection callback."""
        if rc == 0:
            self._connected = True
            _LOGGER.debug("Connected to TV MQTT broker")
            for topic in self._subscriptions:
                client.subscribe(topic)
        else:
            self._connected = False
            _LOGGER.warning("MQTT connection failed: %s", rc)
        self._connect_event.set()

    def _on_disconnect(self, client, userdata, rc, properties=None, reasonCode=None):
        """Handle disconnection callback."""
        self._connected = False
        _LOGGER.debug("Disconnected from TV MQTT broker: %s", rc)

    def _on_message(self, client, userdata, msg):
        """Handle incoming message - marshal to HA event loop."""
        callback = self._subscriptions.get(msg.topic)
        if callback:
            self._hass.loop.call_soon_threadsafe(
                lambda: self._hass.async_create_task(self._safe_callback(callback, msg))
            )

    async def _safe_callback(self, callback, message):
        """Run callback safely - handle both sync and async."""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(message)
            else:
                callback(message)
        except Exception as ex:
            _LOGGER.exception("Error in MQTT callback: %s", ex)

    def disconnect(self):
        """Disconnect from the broker."""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
        self._connected = False
        self._subscriptions.clear()
        _LOGGER.debug("Disconnected from TV MQTT broker")

    def publish(self, topic: str, payload: Any, retain: bool = False) -> bool:
        """Publish message to topic."""
        if not self._client or not self._connected:
            _LOGGER.warning("MQTT client not connected, cannot publish")
            return False
        try:
            result = self._client.publish(topic, payload, qos=0, retain=retain)
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as ex:
            _LOGGER.error("Publish failed: %s", ex)
            return False

    async def async_publish(self, topic: str, payload: Any, retain: bool = False) -> bool:
        """Async publish - runs in executor."""
        return await self._hass.async_add_executor_job(
            self.publish, topic, payload, retain
        )

    def subscribe(self, topic: str, callback: Callable) -> Callable:
        """Subscribe to topic. Returns unsubscribe function."""

        def unsubscribe():
            if topic in self._subscriptions:
                del self._subscriptions[topic]
            if self._client and self._connected:
                self._client.unsubscribe(topic)

        self._subscriptions[topic] = callback
        if self._client and self._connected:
            self._client.subscribe(topic)
        return unsubscribe

    async def async_subscribe(self, topic: str, callback: Callable) -> Callable:
        """Async subscribe - ensures we're connected."""
        return await self._hass.async_add_executor_job(
            self.subscribe, topic, callback
        )

    @property
    def connected(self) -> bool:
        """Return connection status."""
        return self._connected

    @property
    def client_id(self) -> str:
        """Return client ID for topic formatting."""
        return self._client_id
