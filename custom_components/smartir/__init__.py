import aiohttp
from distutils.version import StrictVersion
import logging
import os.path
import voluptuous as vol

from homeassistant.const import (
    ATTR_FRIENDLY_NAME, __version__ as current_ha_version, ATTR_ENTITY_ID, Platform)
import homeassistant.helpers.config_validation as cv

from .constant import *
from .helper import Helper
from .climate import SmartIRClimate

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'smartir'
VERSION = '1.17.9'
MANIFEST_URL = (
    "https://raw.githubusercontent.com/"
    "smartHomeHub/SmartIR/{}/"
    "custom_components/smartir/manifest.json")
REMOTE_BASE_URL = (
    "https://raw.githubusercontent.com/"
    "smartHomeHub/SmartIR/{}/"
    "custom_components/smartir/")
COMPONENT_ABS_DIR = os.path.dirname(
    os.path.abspath(__file__))

CONF_CHECK_UPDATES = 'check_updates'
CONF_UPDATE_BRANCH = 'update_branch'

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Optional(CONF_CHECK_UPDATES, default=True): cv.boolean,
        vol.Optional(CONF_UPDATE_BRANCH, default='master'): vol.In(
            ['master', 'rc'])
    })
}, extra=vol.ALLOW_EXTRA)

SCHEMA_AC_BATCH_COMMAND = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_domain(Platform.CLIMATE),
        vol.Required('mode'): cv.string,
        vol.Optional('temperature'): cv.positive_float,
        vol.Optional('fan'): cv.string,
        vol.Optional('swing'): cv.string,
    }
)

async def async_setup(hass, config):
    """Set up the SmartIR component."""
    conf = config.get(DOMAIN)

    if conf is None:
        return True

    check_updates = conf[CONF_CHECK_UPDATES]
    update_branch = conf[CONF_UPDATE_BRANCH]

    async def _check_updates(service):
        await _update(hass, update_branch)

    async def _update_component(service):
        await _update(hass, update_branch, True)

    async def _send_ac_batch_command(service):
        entity_id = service.data.get(ATTR_ENTITY_ID)
        entity_obj = hass.data[Platform.CLIMATE].get_entity(entity_id)
        if entity_obj is None or not isinstance(entity_obj, SmartIRClimate):
            _LOGGER.warning(f"SmartIR.ac_batch_command: no entity found by {entity_id}")
            return
        entity_obj: SmartIRClimate
        await entity_obj.async_batch_set(service.data.get('mode'),
                                         service.data.get('fan'),
                                         service.data.get('swing'),
                                         service.data.get('temperature'))

    hass.services.async_register(DOMAIN, 'check_updates', _check_updates)
    hass.services.async_register(DOMAIN, 'update_component', _update_component)
    hass.services.async_register(DOMAIN, 'ac_batch_command', _send_ac_batch_command, schema=SCHEMA_AC_BATCH_COMMAND)

    if check_updates:
        await _update(hass, update_branch, False, False)

    return True

async def _update(hass, branch, do_update=False, notify_if_latest=True):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(MANIFEST_URL.format(branch)) as response:
                if response.status == 200:
                    
                    data = await response.json(content_type='text/plain')
                    min_ha_version = data['homeassistant']
                    last_version = data['updater']['version']
                    release_notes = data['updater']['releaseNotes']

                    if StrictVersion(last_version) <= StrictVersion(VERSION):
                        if notify_if_latest:
                            hass.components.persistent_notification.async_create(
                                "You're already using the latest version!", 
                                title='SmartIR')
                        return

                    if StrictVersion(current_ha_version) < StrictVersion(min_ha_version):
                        hass.components.persistent_notification.async_create(
                            "There is a new version of SmartIR integration, but it is **incompatible** "
                            "with your system. Please first update Home Assistant.", title='SmartIR')
                        return

                    if do_update is False:
                        hass.components.persistent_notification.async_create(
                            "A new version of SmartIR integration is available ({}). "
                            "Call the ``smartir.update_component`` service to update "
                            "the integration. \n\n **Release notes:** \n{}"
                            .format(last_version, release_notes), title='SmartIR')
                        return

                    # Begin update
                    files = data['updater']['files']
                    has_errors = False

                    for file in files:
                        try:
                            source = REMOTE_BASE_URL.format(branch) + file
                            dest = os.path.join(COMPONENT_ABS_DIR, file)
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            await Helper.downloader(source, dest)
                        except Exception:
                            has_errors = True
                            _LOGGER.error("Error updating %s. Please update the file manually.", file)

                    if has_errors:
                        hass.components.persistent_notification.async_create(
                            "There was an error updating one or more files of SmartIR. "
                            "Please check the logs for more information.", title='SmartIR')
                    else:
                        hass.components.persistent_notification.async_create(
                            "Successfully updated to {}. Please restart Home Assistant."
                            .format(last_version), title='SmartIR')
    except Exception:
       _LOGGER.error("An error occurred while checking for updates.")
