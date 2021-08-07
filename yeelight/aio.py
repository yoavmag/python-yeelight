# encoding: utf8
import asyncio
import json
import logging
import socket
from typing import Dict

from future.utils import raise_from

from .enums import LightType
from .main import _command_to_send_command
from .main import Bulb
from .main import BulbException
from .main import DEFAULT_PROPS

_LOGGER = logging.getLogger(__name__)

TIMEOUT = 5
PING_INTERVAL = 60

KEY_CONNECTED = "connected"


def _async_command(f):
    """
    A decorator that wraps a function and enables effects.

    This decorator can only be used with async functions
    because it needs to call an awaitable.
    """

    async def wrapper(*args, **kw):
        """A decorator that wraps a function and enables effects."""
        self = args[0]
        cmd = await self.async_send_command(
            *_command_to_send_command(
                self,
                *(await f(*args, **kw)),
                kw.get("effect", self.effect),
                kw.get("duration", self.duration),
                kw.get("power_mode", self.power_mode)
            )
        )
        result = cmd.get("result", [])
        if result:
            return result[0]

    return wrapper


class AsyncBulb(Bulb):
    """Asyncio support for Bulb."""

    def __init__(self, *args, **kwargs) -> None:
        # Asyncio
        super().__init__(*args, **kwargs)
        self._async_callback = None
        self._async_pending_commands: Dict[int, asyncio.Future] = {}
        self._async_listen_task = None
        self._async_reconnect_task = None
        self._async_writer = None
        self._async_reader = None
        self._async_cmd_id = 0

    async def async_send_command(self, method, params):
        """Send a command to the bulb and wait for the result."""
        future = await self._async_send_command(method, params)
        response = await asyncio.wait_for(future, TIMEOUT)

        if "error" in response:
            raise BulbException(response["error"])

        return response

    async def _async_send_command(self, method, params, create_future=True):
        """Send the command."""
        self._async_cmd_id += 1
        request_id = self._async_cmd_id

        if create_future:
            future = asyncio.Future()
            self._async_pending_commands[request_id] = future

            def clean_up(future):
                if future.cancelled():
                    self._async_pending_commands.pop(request_id, None)

            future.add_done_callback(clean_up)

        command = {"id": request_id, "method": method, "params": params}
        _LOGGER.debug("%s > %s", self, command)
        self._async_writer.write((json.dumps(command) + "\r\n").encode("utf8"))
        await self._async_writer.drain()
        self._async_writer.write(b" ")
        await self._async_writer.drain()
        _LOGGER.debug("%s: Finished _async_send_command", self)
        return future if create_future else request_id

    async def _async_run_listen(self):
        """Backend for async_listen."""
        _LOGGER.debug("%s: Starting listen task", self)
        while self._is_listening:
            try:
                await self._async_connection_loop()
            finally:
                self._async_close_reader_writer()
                if self._async_callback:
                    self._async_callback({KEY_CONNECTED: False})
                await asyncio.sleep(TIMEOUT)
                await self._async_reconnect_loop()

    async def _async_reconnect_loop(self):
        _LOGGER.debug("%s: Starting reconnect", self)
        while self._is_listening:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self._ip, self._port), TIMEOUT
                )
            except (asyncio.TimeoutError, socket.error):
                await asyncio.sleep(TIMEOUT)
            else:
                _LOGGER.debug("%s: Reconnected successfully", self)
                self._async_connected(writer, reader)
                return

    async def _async_connection_loop(self):
        timeouts = 0
        ping_id = -1
        while self._is_listening:
            try:
                _LOGGER.debug("%s: Waiting for line", self)
                line = await asyncio.wait_for(
                    self._async_reader.readline(), PING_INTERVAL + TIMEOUT
                )
            except asyncio.TimeoutError:
                timeouts += 1
                if timeouts == 2:
                    _LOGGER.debug("%s: Timeout waiting for line", self)
                    return
                _LOGGER.debug(
                    "%s: No data in %s seconds, pinging bulb to make sure its still connected",
                    self,
                    PING_INTERVAL + TIMEOUT,
                )
                ping_id = await self._async_send_command(
                    "get_prop", ["power"], create_future=False
                )
                continue
            except socket.error as ex:
                _LOGGER.debug("%s: Socket error: %s", self, ex)
                # back off
                await asyncio.sleep(TIMEOUT)
                return
            else:
                _LOGGER.debug("%s: Success got line: %s", self, line)
                timeouts = 0

            if not line:
                _LOGGER.debug("%s: Bulb closed the connection", self)
                return

            try:
                decoded_line = json.loads(line.decode("utf8").rstrip())
            except ValueError:
                _LOGGER.error("%s: Invalid data: %s", self, line)
                continue

            if "id" in decoded_line:
                future = self._async_pending_commands.pop(decoded_line["id"], None)
                if future:
                    future.set_result(decoded_line)
                elif decoded_line["id"] == ping_id:
                    _LOGGER.debug("%s: Ping result received: %s", self, decoded_line)
                    data = {"power": decoded_line["result"][0]}
                    self._set_last_properties(data, update=True)
                    data.update({KEY_CONNECTED: True})
                    self._async_callback(data)
                    continue

            if "error" in decoded_line:
                if decoded_line["error"].get("message") == "client quota exceeded":
                    _LOGGER.debug(
                        "%s: client quota exceeded, dropping connection and reconnecting",
                        self,
                    )
                    return

            if decoded_line.get("method") != "props":
                _LOGGER.debug("%s: props not in line: %s", self, line)
                continue

            # Update notification received
            _LOGGER.debug("%s: New props received: %s", self, decoded_line)
            self._set_last_properties(decoded_line["params"], update=True)
            data = decoded_line["params"]
            data.update({KEY_CONNECTED: True})
            self._async_callback(data)

    def _async_connected(self, writer, reader):
        """Called when we are successfully connected to the bulb."""
        self._async_cmd_id = 0
        self._async_writer = writer
        self._async_reader = reader

    async def async_listen(self, callback):
        """
        Listen to state update notifications.

        This function is blocking until a socket error occurred or being stopped by
        ``stop_listening``. It should be run in an ``asyncio`` task.

        The callback function should take one parameter, containing the new/updates
        properties. It will be called when ``last_properties`` is updated.

        Reconnection happens automaticlly if the socket is closed until
        async_stop_listening is called

        :param callable callback: A callback function to receive state update notification.
        """
        self._async_callback = callback

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._ip, self._port), 10
            )
        except asyncio.TimeoutError as ex:
            raise_from(BulbException("Failed to connecto the the bulb."), ex)
        except socket.error as ex:
            raise_from(BulbException("Failed to read from the socket."), ex)

        self._is_listening = True
        self._async_connected(writer, reader)
        self._async_listen_task = asyncio.ensure_future(self._async_run_listen())
        self._async_callback({KEY_CONNECTED: True})

    def _async_stop_listen_task(self):
        if self._async_listen_task:
            self._async_listen_task.cancel()
            self._async_listen_task = None

    def _async_close_reader_writer(self):
        self._async_pending_commands = {}
        if self._async_writer:
            self._async_writer.close()
            self._async_writer = None
        self._async_reader = None

    async def async_stop_listening(self):
        """Stop listening to notifications."""
        self._is_listening = False
        self._async_stop_listen_task()
        self._async_close_reader_writer()
        self._async_callback = None

    async def async_get_properties(
        self, requested_properties=DEFAULT_PROPS,
    ):
        """
        Retrieve and return the properties of the bulb.

        This method also updates ``last_properties`` when it is called.

        The ``current_brightness`` property is calculated by the library (i.e. not returned
        by the bulb), and indicates the current brightness of the lamp, aware of night light
        mode. It is 0 if the lamp is off, and None if it is unknown.

        :param list requested_properties: The list of properties to request from the bulb.
                                          By default, this does not include ``flow_params``.

        :returns: A dictionary of param: value items.
        :rtype: dict
        """
        # When we are in music mode, the bulb does not respond to queries
        # therefore we need to keep the state up-to-date ourselves
        if self._music_mode:
            return self._last_properties

        response = await self.async_send_command("get_prop", requested_properties)
        if response is not None and "result" in response:
            properties = response["result"]
            properties = [x if x else None for x in properties]
            new_values = dict(zip(requested_properties, properties))

        self._set_last_properties(new_values, update=False)

        return self._last_properties

    async def async_ensure_on(self):
        """Turn the bulb on if it is off."""
        if self._music_mode is True or self.auto_on is False:
            return

        await self.async_get_properties()

        if self._last_properties["power"] != "on":
            await self.async_turn_on()

    @_async_command
    async def async_set_color_temp(self, degrees, light_type=LightType.Main, **kwargs):
        """
        Set the bulb's color temperature.

        :param int degrees: The degrees to set the color temperature to (min/max are
                            specified by the model's capabilities, or 1700-6500).
        :param yeelight.LightType light_type: Light type to control.
        """
        await self.async_ensure_on()
        return self._set_color_temp(degrees, light_type=light_type, **kwargs)

    @_async_command
    async def async_set_rgb(
        self, red, green, blue, light_type=LightType.Main, **kwargs
    ):
        """
        Set the bulb's RGB value.

        :param int red:   The red value to set (0-255).
        :param int green: The green value to set (0-255).
        :param int blue:  The blue value to set (0-255).
        :param yeelight.LightType light_type:
                          Light type to control.
        """
        await self.async_ensure_on()
        return self._set_rgb(red, green, blue, light_type=light_type, **kwargs)

    @_async_command
    async def async_set_adjust(self, action, prop, **kwargs):
        """
        Adjust a parameter.

        I don't know what this is good for. I don't know how to use it, or why.
        I'm just including it here for completeness, and because it was easy,
        but it won't get any particular love.

        :param str action: The direction of adjustment. Can be "increase",
                           "decrease" or "circle".
        :param str prop:   The property to adjust. Can be "bright" for
                           brightness, "ct" for color temperature and "color"
                           for color. The only action for "color" can be
                           "circle". Why? Who knows.
        """
        return self._set_adjust(action, prop, **kwargs)

    @_async_command
    async def async_set_hsv(
        self, hue, saturation, value=None, light_type=LightType.Main, **kwargs
    ):
        """
        Set the bulb's HSV value.

        :param int hue:        The hue to set (0-359).
        :param int saturation: The saturation to set (0-100).
        :param int value:      The value to set (0-100). If omitted, the bulb's
                               brightness will remain the same as before the
                               change.
        :param yeelight.LightType light_type: Light type to control.
        """
        await self.async_ensure_on()
        return self._set_hsv(hue, saturation, value, light_type, **kwargs)

    @_async_command
    async def async_set_brightness(
        self, brightness, light_type=LightType.Main, **kwargs
    ):
        """
        Set the bulb's brightness.

        :param int brightness: The brightness value to set (1-100).
        :param yeelight.LightType light_type: Light type to control.
        """
        await self.async_ensure_on()
        return self._set_brightness(brightness, light_type=light_type, **kwargs)

    @_async_command
    async def async_turn_on(self, light_type=LightType.Main, **kwargs):
        """
        Turn the bulb on.

        :param yeelight.LightType light_type: Light type to control.
        """
        return self._turn_on(light_type=light_type, **kwargs)

    @_async_command
    async def async_turn_off(self, light_type=LightType.Main, **kwargs):
        """
        Turn the bulb off.

        :param yeelight.LightType light_type: Light type to control.
        """
        return self._turn_off(light_type=light_type, **kwargs)

    @_async_command
    async def async_toggle(self, light_type=LightType.Main, **kwargs):
        """
        Toggle the bulb on or off.

        :param yeelight.LightType light_type: Light type to control.
        """
        return self._toggle(light_type=light_type, **kwargs)

    @_async_command
    async def async_dev_toggle(self, **kwargs):
        """Toggle the main light and the ambient on or off."""
        return self._dev_toggle(**kwargs)

    @_async_command
    async def async_set_default(self, light_type=LightType.Main, **kwargs):
        """
        Set the bulb's current state as the default, which is what the bulb will be set to on power on.

        If you get a "general error" setting this, yet the bulb reports as supporting `set_default` during
        discovery, disable "auto save settings" in the YeeLight app.

        :param yeelight.LightType light_type: Light type to control.
        """
        return self._set_default(light_type=light_type, **kwargs)

    @_async_command
    async def async_set_name(self, name, **kwargs):
        """
        Set the bulb's name.

        :param str name: The string you want to set as the bulb's name.
        """
        return self._set_name(name, **kwargs)

    @_async_command
    async def async_start_flow(self, flow, light_type=LightType.Main, **kwargs):
        """
        Start a flow.

        :param yeelight.Flow flow: The Flow instance to start.
        """
        await self.async_ensure_on()
        return self._start_start_flow(flow, light_type=light_type, **kwargs)

    @_async_command
    async def async_stop_flow(self, light_type=LightType.Main, **kwargs):
        """
        Stop a flow.

        :param yeelight.LightType light_type: Light type to control.
        """
        return self._stop_flow(light_type=light_type, **kwargs)

    @_async_command
    async def async_set_scene(
        self, scene_class, *args, light_type=LightType.Main, **kwargs
    ):
        """
        Set the light directly to the specified state.

        If the light is off, it will first be turned on.

        :param yeelight.SceneClass scene_class: The YeeLight scene class to use.

        * `COLOR` changes the light to the specified RGB color and brightness.

            Arguments:
            * **red** (*int*)         – The red value to set (0-255).
            * **green** (*int*)       – The green value to set (0-255).
            * **blue** (*int*)        – The blue value to set (0-255).
            * **brightness** (*int*)  – The brightness value to set (1-100).

        * `HSV` changes the light to the specified HSV color and brightness.

            Arguments:
            * **hue** (*int*)         – The hue to set (0-359).
            * **saturation** (*int*)  – The saturation to set (0-100).
            * **brightness** (*int*)  – The brightness value to set (1-100).

        * `CT` changes the light to the specified color temperature.

            Arguments:
            * **degrees** (*int*)     – The degrees to set the color temperature to (min/max are specified by the
            model's capabilities, or 1700-6500).
            * **brightness** (*int*)  – The brightness value to set (1-100).

        * `CF` starts a color flow.

            Arguments:
            * **flow** (`yeelight.Flow`)  – The Flow instance to start.

        * `AUTO_DELAY_OFF` turns the light on to the specified brightness and sets a timer to turn it back off after the
          given number of minutes.

            Arguments:
            * **brightness** (*int*)     – The brightness value to set (1-100).
            * **minutes** (*int*)        – The minutes to wait before automatically turning the light off.

        :param yeelight.LightType light_type: Light type to control.
        """
        return self._set_scene(scene_class, *args, light_type=light_type, **kwargs)

    @_async_command
    async def async_cron_add(self, event_type, value, **kwargs):
        """
        Add an event to cron.

        Example::

        >>> bulb.cron_add(CronType.off, 10)

        :param yeelight.CronType event_type: The type of event. Currently,
                                                   only ``CronType.off``.
        """
        return self._cron_add(event_type, value, **kwargs)

    @_async_command
    async def async_cron_get(self, event_type, **kwargs):
        """
        Retrieve an event from cron.

        :param yeelight.CronType event_type: The type of event. Currently,
                                                   only ``CronType.off``.
        """
        return self._cron_get(event_type, **kwargs)

    @_async_command
    async def cron_del(self, event_type, **kwargs):
        """
        Remove an event from cron.

        :param yeelight.CronType event_type: The type of event. Currently,
                                                   only ``CronType.off``.
        """
        return self._cron_del(event_type, **kwargs)

    def __repr__(self):
        return "AsyncBulb<{ip}:{port}, type={type}>".format(
            ip=self._ip, port=self._port, type=self.bulb_type
        )

    async def async_set_power_mode(self, mode):
        """
        Set the light power mode.

        If the light is off it will be turned on.

        :param yeelight.PowerMode mode: The mode to switch to.
        """
        return await self.async_turn_on(power_mode=mode)
