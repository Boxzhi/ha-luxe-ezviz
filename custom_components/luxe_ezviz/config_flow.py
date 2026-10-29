"""Native HA setup/reconfigure for Luxe EZVIZ."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    FileSelector, FileSelectorConfig, TextSelector, TextSelectorConfig, TextSelectorType
)

from .encryption import parse_encryption_state
from .image_manager import InvalidProductImage, async_save_image, async_delete_image
from .api import (
    EzvizApiError,
    EzvizAuthError,
    EzvizClient,
    EzvizConnectionError,
    EzvizDeviceError,
    EzvizDeviceNotFoundError,
    EzvizInvalidChannelError,
    EzvizInvalidSerialError,
)
from .const import (
    CONF_APP_KEY,
    CONF_APP_SECRET,
    CONF_CHANNEL,
    CONF_IMAGE_UPLOAD,
    CONF_IMAGE_REMOVE,
    CONF_DEVICE_SERIAL,
    CONF_VERIFY_CODE,
    DEFAULT_CHANNEL,
    DOMAIN,
)

_SERIAL_RE = re.compile(r"[A-Za-z0-9_-]{4,64}\Z")


class LuxeEzvizConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure one EZVIZ developer app and camera."""

    VERSION = 1

    @staticmethod
    def _schema(defaults: dict | None = None, *, reconfigure: bool = False):
        current = defaults or {}
        # For reconfigure, blank secret/code means keep the saved value; never
        # expose stored secrets as form defaults or suggestion values.
        return vol.Schema({
            vol.Required(CONF_APP_KEY, default=current.get(CONF_APP_KEY, "")): vol.All(str, vol.Length(min=1, max=128)),
            vol.Required(CONF_APP_SECRET, default=""): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_DEVICE_SERIAL, default=current.get(CONF_DEVICE_SERIAL, "")): vol.All(str, vol.Length(min=4, max=64)),
            vol.Required(CONF_VERIFY_CODE, default=""): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_CHANNEL, default=current.get(CONF_CHANNEL, DEFAULT_CHANNEL)): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
            **({vol.Optional(CONF_IMAGE_UPLOAD): FileSelector(FileSelectorConfig(accept=".png,.jpg,.jpeg,.webp"))} if not reconfigure else {}),
        })

    @staticmethod
    def _initial_name(device_info: dict, serial: str) -> str:
        """Cloud nickname is a display label, never a device identity."""
        name = device_info.get("deviceName")
        if isinstance(name, str) and name.strip():
            return name.strip()[:64]
        model = device_info.get("model")
        if isinstance(model, str) and model.strip():
            return f"{model.strip()[:42]} · {serial[-4:]}"
        return f"萤石摄像机 · {serial[-4:]}"

    async def _validate(self, values: dict[str, Any]) -> tuple[str | None, dict | None]:
        """Check key/secret and access to the named device, not its video code."""
        if not _SERIAL_RE.fullmatch(values[CONF_DEVICE_SERIAL]):
            return "invalid_serial", None
        if not values[CONF_APP_SECRET] or not values[CONF_VERIFY_CODE]:
            return "missing_credentials", None
        client = EzvizClient(async_get_clientsession(self.hass))
        try:
            token, _expiry = await client.async_get_token(
                values[CONF_APP_KEY], values[CONF_APP_SECRET]
            )
            device_info = await client.async_device_info(token, values[CONF_DEVICE_SERIAL])
            if parse_encryption_state(device_info) is None:
                return "encryption_unknown", None
            channels = await client.async_device_channels(
                token, values[CONF_DEVICE_SERIAL]
            )
            if not any(
                str(channel.get("channelNo")) == str(values[CONF_CHANNEL])
                for channel in channels
            ):
                return "invalid_channel", None
        except EzvizAuthError:
            return "invalid_auth", None
        except EzvizInvalidSerialError:
            return "invalid_serial", None
        except EzvizDeviceNotFoundError:
            return "device_not_found", None
        except EzvizInvalidChannelError:
            return "invalid_channel", None
        except EzvizDeviceError:
            return "device_permission", None
        except (EzvizConnectionError, EzvizApiError):
            return "cannot_connect", None
        return None, device_info

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a device keyed only by its immutable EZVIZ serial number."""
        errors: dict[str, str] = {}
        if user_input is not None:
            values = dict(user_input)
            upload_id = values.pop(CONF_IMAGE_UPLOAD, None)
            values[CONF_DEVICE_SERIAL] = values[CONF_DEVICE_SERIAL].strip().upper()
            # HA tracks serial uniqueness across all entries; names may repeat.
            if _SERIAL_RE.fullmatch(values[CONF_DEVICE_SERIAL]):
                await self.async_set_unique_id(values[CONF_DEVICE_SERIAL])
                self._abort_if_unique_id_configured()
            error, info = await self._validate(values)
            if error:
                errors["base"] = error
            else:
                if upload_id:
                    try:
                        await async_save_image(self.hass, upload_id, values[CONF_DEVICE_SERIAL])
                    except (InvalidProductImage, OSError, KeyError, ValueError):
                        errors[CONF_IMAGE_UPLOAD] = "invalid_image"
                if not errors:
                    return self.async_create_entry(
                        title=self._initial_name(info, values[CONF_DEVICE_SERIAL]),
                        data=values,
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=self._schema(user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update credentials without rewriting HA's user-editable device title."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            values = dict(user_input)
            values[CONF_DEVICE_SERIAL] = values[CONF_DEVICE_SERIAL].strip().upper()
            for field in (CONF_APP_SECRET, CONF_VERIFY_CODE):
                if not values[field]:
                    values[field] = entry.data[field]
            error, _info = await self._validate(values)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(values[CONF_DEVICE_SERIAL])
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry, data_updates=values
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._schema(
                user_input if user_input is not None else dict(entry.data),
                reconfigure=True,
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Start a credential replacement flow."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Request fresh app credentials while retaining camera details."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            values = dict(entry.data)
            values.update(user_input)
            error, _info = await self._validate(values)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(entry.data[CONF_DEVICE_SERIAL])
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_APP_KEY,
                    default=(user_input or entry.data)[CONF_APP_KEY],
                ): str,
                vol.Required(CONF_APP_SECRET): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Per-device optional image management, without reconfiguring credentials."""
        return LuxeEzvizOptionsFlow()


class LuxeEzvizOptionsFlow(OptionsFlow):
    """Upload, replace or remove the current camera's product photo."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            upload_id = user_input.get(CONF_IMAGE_UPLOAD)
            remove = bool(user_input.get(CONF_IMAGE_REMOVE, False))
            serial = self.config_entry.data[CONF_DEVICE_SERIAL]
            if upload_id and remove:
                errors["base"] = "image_conflict"
            elif upload_id:
                try:
                    await async_save_image(self.hass, upload_id, serial)
                except (InvalidProductImage, OSError, KeyError, ValueError):
                    errors[CONF_IMAGE_UPLOAD] = "invalid_image"
            elif remove:
                try:
                    await async_delete_image(self.hass, serial)
                except OSError:
                    errors["base"] = "image_error"
            if not errors:
                return self.async_create_entry(title="", data=dict(self.config_entry.options))
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_IMAGE_UPLOAD): FileSelector(FileSelectorConfig(accept=".png,.jpg,.jpeg,.webp")),
                vol.Optional(CONF_IMAGE_REMOVE, default=False): bool,
            }),
            errors=errors,
        )
