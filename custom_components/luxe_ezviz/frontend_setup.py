"""Register packaged frontend assets and an idempotent Lovelace module."""
from __future__ import annotations
import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant

from .sdk import sdk_directory

_LOGGER = logging.getLogger(__name__)
CARD_URL='/luxe_ezviz/static/luxe-ezviz-card.js'
VERSION='1.1.2'
ASSET_VERSION='1.1.2-ezuikit-9.0.24'
CARD_RESOURCE=f'{CARD_URL}?v={ASSET_VERSION}'

async def async_setup_frontend(hass: HomeAssistant) -> None:
    paths=[
        StaticPathConfig('/luxe_ezviz/static',str(Path(__file__).parent/'frontend'),False),
        StaticPathConfig('/luxe_ezviz/sdk',str(sdk_directory(hass)),False),
    ]
    await hass.http.async_register_static_paths(paths)
    lovelace=hass.data.get(LOVELACE_DATA)
    if lovelace is None:
        _LOGGER.warning('Lovelace not yet available; card resource must be added manually: %s',CARD_RESOURCE)
        return
    if getattr(lovelace,'resource_mode',None)=='yaml':
        _LOGGER.warning('Lovelace resources use YAML mode; add a module resource manually: %s',CARD_RESOURCE)
        return
    resources=lovelace.resources
    # IMPORTANT: Never call async_items/create before the lazy-loaded store
    # has loaded, as it can wipe all preexisting Lovelace resources.
    await resources.async_get_info()
    matches=[item for item in resources.async_items() if item.get('url','').split('?')[0]==CARD_URL]
    if matches:
        for item in matches:
            if item.get('url') != CARD_RESOURCE or item.get('res_type')!='module':
                await resources.async_update_item(item['id'], {'res_type':'module','url':CARD_RESOURCE})
    else:
        await resources.async_create_item({'res_type':'module','url':CARD_RESOURCE})
