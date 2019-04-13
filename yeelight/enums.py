from enum import Enum, IntEnum


class CronType(Enum):
    """The type of event in cron."""

    off = 0


class PowerMode(IntEnum):
    """Power mode of the light."""

    LAST = 0
    NORMAL = 1
    RGB = 2
    HSV = 3
    COLOR_FLOW = 4
    MOONLIGHT = 5


class BulbType(Enum):
    """
    The bulb's type.

    This is either `White` (for monochrome bulbs), `Color` (for color bulbs), `WhiteTemp` (for white bulbs with
    configurable color temperature), `WhiteTempMood` for white bulbs with mood lighting (like the JIAOYUE 650 LED ceiling
    light), or `Unknown` if the properties have not been fetched yet.
    """

    Unknown = -1
    White = 0
    Color = 1
    WhiteTemp = 2
    WhiteTempMood = 3


class LightType(IntEnum):
    """Type of light to control."""

    Main = 0
    Ambient = 1


class SetSceneClass(IntEnum):
    """

    class ( as named in Yeelight docs ) specifies how set_scene method should act

    `color` means change the smart LED to specified color and brightness.
    `hsv` means change the smart LED to specified color and brightness.
    `ct` means change the smart LED to specified ct and brightness.
    `cf` means start a color flow in specified fashion.
    `auto_delay_off` means turn on the smart LED to specified.
    """

    COLOR = 0
    HSV = 1
    CT = 2
    CF = 3
    AUTO_DELAY_OFF = 4
