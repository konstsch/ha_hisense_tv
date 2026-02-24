"""Hisense TV config flow."""
import asyncio
import json
from json.decoder import JSONDecodeError
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import CONF_IP_ADDRESS, CONF_MAC, CONF_NAME, CONF_PIN
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_MQTT_CLIENT_ID,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_PORT,
    CONF_MQTT_USERNAME,
    DEFAULT_CLIENT_ID,
    DEFAULT_MQTT_PASSWORD,
    DEFAULT_MQTT_PORT,
    DEFAULT_MQTT_USERNAME,
    DEFAULT_NAME,
    DOMAIN,
)
from .mqtt_client import HisenseMqttClient

_LOGGER = logging.getLogger(__name__)


class HisenseTvFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Hisense TV config flow."""

    VERSION = 2
    task_mqtt = None
    task_auth = None

    def __init__(self):
        """Initialize the config flow."""
        self._mac = None
        self._name = None
        self._unsubscribe_auth = None
        self._unsubscribe_sourcelist = None
        self._auth_event = None
        self._mqtt_client = None

    def _on_pin_needed(self, message):
        if message.retain:
            _LOGGER.debug("_on_pin_needed - skip retained message")
            return
        _LOGGER.debug("_on_pin_needed")
        try:
            payload_raw = message.payload
            if isinstance(payload_raw, bytes):
                payload_raw = payload_raw.decode("utf-8")
            payload = json.loads(payload_raw) if payload_raw else {}
        except (JSONDecodeError, UnicodeDecodeError):
            payload = {}
        if payload.get("result") == 1:
            _LOGGER.debug("_on_pin_needed - already authenticated (result=1)")
            self._unsubscribe()
            self.task_auth = True
        else:
            self._unsubscribe()
            self.task_auth = False
        if self._auth_event is not None:
            self._auth_event.set()

    def _on_pin_not_needed(self, message):
        if message.retain:
            _LOGGER.debug("_on_pin_not_needed - skip retained message")
            return
        _LOGGER.debug("_on_pin_not_needed")
        self._unsubscribe()
        self.task_auth = True
        if self._auth_event is not None:
            self._auth_event.set()

    def _on_authcode_response(self, message):
        self._unsubscribe()
        try:
            payload_raw = message.payload
            if isinstance(payload_raw, bytes):
                payload_raw = payload_raw.decode("utf-8")
            payload = json.loads(payload_raw)
        except (JSONDecodeError, UnicodeDecodeError):
            payload = {}
        _LOGGER.debug("_on_authcode_response %s", payload)
        self.task_auth = payload.get("result") == 1
        if self._auth_event is not None:
            self._auth_event.set()

    def _unsubscribe(self):
        _LOGGER.debug("_unsubscribe")
        if self._unsubscribe_auth is not None:
            self._unsubscribe_auth()
            self._unsubscribe_auth = None
        if self._unsubscribe_sourcelist is not None:
            self._unsubscribe_sourcelist()
            self._unsubscribe_sourcelist = None

    async def async_step_user(self, user_input=None) -> FlowResult:
        if self.task_auth is True:
            _LOGGER.debug("async_step_user - task_auth is True")
            return self.async_show_progress_done(next_step_id="finish")

        if self.task_auth is False:
            self.task_auth = None
            _LOGGER.debug("async_step_user - task_auth is False")
            return self.async_show_progress_done(next_step_id="auth")

        if user_input is None:
            _LOGGER.debug("async_step_user - user_input is None")
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                        vol.Required(CONF_MAC): str,
                        vol.Required(CONF_IP_ADDRESS): str,
                        vol.Optional(CONF_MQTT_PORT, default=DEFAULT_MQTT_PORT): int,
                        vol.Optional(
                            CONF_MQTT_USERNAME, default=DEFAULT_MQTT_USERNAME
                        ): str,
                        vol.Optional(
                            CONF_MQTT_PASSWORD, default=DEFAULT_MQTT_PASSWORD
                        ): str,
                        vol.Optional(
                            CONF_MQTT_CLIENT_ID, default=DEFAULT_CLIENT_ID
                        ): str,
                        vol.Optional("no_pin", default=True): bool,
                    }
                ),
            )

        _LOGGER.debug("async_step_user - set task_mqtt")
        self.task_mqtt = {
            CONF_MAC: user_input.get(CONF_MAC),
            CONF_NAME: user_input.get(CONF_NAME),
            CONF_IP_ADDRESS: user_input.get(CONF_IP_ADDRESS),
            CONF_MQTT_PORT: user_input.get(CONF_MQTT_PORT, DEFAULT_MQTT_PORT),
            CONF_MQTT_USERNAME: user_input.get(
                CONF_MQTT_USERNAME, DEFAULT_MQTT_USERNAME
            ),
            CONF_MQTT_PASSWORD: user_input.get(
                CONF_MQTT_PASSWORD, DEFAULT_MQTT_PASSWORD
            ),
            CONF_MQTT_CLIENT_ID: user_input.get(
                CONF_MQTT_CLIENT_ID, DEFAULT_CLIENT_ID
            ),
        }

        no_pin = user_input.get("no_pin", True)
        if no_pin:
            self.task_auth = None
            check_done = asyncio.Event()

            async def _check_and_finish():
                success = await self._check_connection_sourcelist_only()
                if success:
                    self.task_auth = True
                else:
                    self.task_auth = False
                check_done.set()

            async def _wait_for_check():
                await check_done.wait()

            self.hass.async_create_task(_check_and_finish())
            progress_task = self.hass.async_create_task(_wait_for_check())
            return self.async_show_progress(
                step_id="user",
                progress_action="progress_action",
                progress_task=progress_task,
            )

        self._auth_event = asyncio.Event()
        await self._check_authentication()

        async def _wait_for_auth():
            try:
                await asyncio.wait_for(self._auth_event.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout waiting for TV MQTT response")
                self.task_auth = False
                self._unsubscribe()

        progress_task = self.hass.async_create_task(_wait_for_auth())
        return self.async_show_progress(
            step_id="user",
            progress_action="progress_action",
            progress_task=progress_task,
        )

    async def _check_connection_sourcelist_only(self) -> bool:
        """Check connection by waiting for sourcelist response."""
        client_id = self.task_mqtt[CONF_MQTT_CLIENT_ID]
        self._mqtt_client = HisenseMqttClient(
            hass=self.hass,
            host=self.task_mqtt[CONF_IP_ADDRESS],
            port=self.task_mqtt.get(CONF_MQTT_PORT, DEFAULT_MQTT_PORT),
            username=self.task_mqtt.get(CONF_MQTT_USERNAME, DEFAULT_MQTT_USERNAME),
            password=self.task_mqtt.get(CONF_MQTT_PASSWORD, DEFAULT_MQTT_PASSWORD),
            client_id=client_id,
        )
        if not await self._mqtt_client.async_connect():
            return False

        self._auth_event = asyncio.Event()
        self._unsubscribe_sourcelist = await self._mqtt_client.async_subscribe(
            topic="/remoteapp/mobile/%s/ui_service/data/sourcelist" % client_id,
            callback=self._on_pin_not_needed,
        )
        await self._mqtt_client.async_publish(
            topic="/remoteapp/tv/ui_service/%s/actions/gettvstate" % client_id,
            payload="",
        )
        await self._mqtt_client.async_publish(
            topic="/remoteapp/tv/ui_service/%s/actions/sourcelist" % client_id,
            payload="",
        )

        try:
            await asyncio.wait_for(self._auth_event.wait(), timeout=30.0)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self._unsubscribe()
            self._mqtt_client.disconnect()
            self._mqtt_client = None

    async def _check_authentication(self):
        """Check authentication using direct MQTT client."""
        client_id = self.task_mqtt[CONF_MQTT_CLIENT_ID]
        self._mqtt_client = HisenseMqttClient(
            hass=self.hass,
            host=self.task_mqtt[CONF_IP_ADDRESS],
            port=self.task_mqtt.get(CONF_MQTT_PORT, DEFAULT_MQTT_PORT),
            username=self.task_mqtt.get(CONF_MQTT_USERNAME, DEFAULT_MQTT_USERNAME),
            password=self.task_mqtt.get(CONF_MQTT_PASSWORD, DEFAULT_MQTT_PASSWORD),
            client_id=client_id,
        )
        if not await self._mqtt_client.async_connect():
            self.task_auth = False
            if self._auth_event:
                self._auth_event.set()
            return

        self._unsubscribe_auth = await self._mqtt_client.async_subscribe(
            topic="/remoteapp/mobile/%s/ui_service/data/authentication" % client_id,
            callback=self._on_pin_needed,
        )
        self._unsubscribe_sourcelist = await self._mqtt_client.async_subscribe(
            topic="/remoteapp/mobile/%s/ui_service/data/sourcelist" % client_id,
            callback=self._on_pin_not_needed,
        )
        await self._mqtt_client.async_publish(
            topic="/remoteapp/tv/ui_service/%s/actions/gettvstate" % client_id,
            payload="",
        )
        await self._mqtt_client.async_publish(
            topic="/remoteapp/tv/ui_service/%s/actions/sourcelist" % client_id,
            payload="",
        )

    async def async_step_reauth(self, user_input=None):
        """Reauth handler."""
        _LOGGER.debug("async_step_reauth: %s", user_input)
        self.task_auth = None
        return await self.async_step_auth(user_input=user_input)

    async def async_step_auth(self, user_input=None):
        """Auth handler."""
        if self.task_auth is True:
            _LOGGER.debug("async_step_auth - task_auth is True -> finish")
            return self.async_show_progress_done(next_step_id="finish")

        if self.task_auth is False:
            _LOGGER.debug("async_step_auth - task_auth is False ->  reauth")
            return self.async_show_progress_done(next_step_id="reauth")

        if user_input is None:
            self.task_auth = None
            _LOGGER.debug("async_step_auth - user_input is None -> show form")
            return self.async_show_form(
                step_id="auth",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_PIN): int,
                    }
                ),
            )
        else:
            _LOGGER.debug("async_step_auth send authentication: %s", user_input)
            client_id = self.task_mqtt[CONF_MQTT_CLIENT_ID]
            self._auth_event = asyncio.Event()
            self._unsubscribe_auth = await self._mqtt_client.async_subscribe(
                topic="/remoteapp/mobile/%s/ui_service/data/authenticationcode"
                % client_id,
                callback=self._on_authcode_response,
            )
            payload = json.dumps({"authNum": user_input.get(CONF_PIN)})
            await self._mqtt_client.async_publish(
                topic="/remoteapp/tv/ui_service/%s/actions/authenticationcode"
                % client_id,
                payload=payload,
            )

            async def _wait_for_auth():
                try:
                    await asyncio.wait_for(self._auth_event.wait(), timeout=30.0)
                except asyncio.TimeoutError:
                    _LOGGER.warning("Timeout waiting for TV auth response")
                    self.task_auth = False
                    self._unsubscribe()

            progress_task = self.hass.async_create_task(_wait_for_auth())
            return self.async_show_progress(
                step_id="auth",
                progress_action="progress_action",
                progress_task=progress_task,
            )

    async def async_step_finish(self, user_input=None):
        """Finish config flow."""
        _LOGGER.debug("async_step_finish")
        if self._mqtt_client:
            self._mqtt_client.disconnect()
            self._mqtt_client = None

        if self.source == SOURCE_REAUTH:
            entry = self._get_reauth_entry()
            return self.async_update_reload_and_abort(entry, data=entry.data)

        await self.async_set_unique_id(self.task_mqtt[CONF_MAC])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=self.task_mqtt[CONF_NAME], data=self.task_mqtt
        )

    async def async_step_import(self, data):
        """Handle import from YAML."""
        _LOGGER.debug("async_step_import")
        entry_data = dict(data)
        entry_data.setdefault(CONF_MQTT_PORT, DEFAULT_MQTT_PORT)
        entry_data.setdefault(CONF_MQTT_USERNAME, DEFAULT_MQTT_USERNAME)
        entry_data.setdefault(CONF_MQTT_PASSWORD, DEFAULT_MQTT_PASSWORD)
        entry_data.setdefault(CONF_MQTT_CLIENT_ID, DEFAULT_CLIENT_ID)
        await self.async_set_unique_id(entry_data[CONF_MAC])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=entry_data[CONF_NAME], data=entry_data)
