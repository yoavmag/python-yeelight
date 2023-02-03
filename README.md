Description
===========


[![image](https://gitlab.com/stavros/python-yeelight/badges/master/pipeline.svg)](https://gitlab.com/stavros/python-yeelight/pipelines)

[![image](https://gitlab.com/stavros/python-yeelight/badges/master/coverage.svg)](https://gitlab.com/stavros/python-yeelight/commits/master)

[![image](https://img.shields.io/pypi/v/yeelight.svg)](https://pypi.python.org/pypi/yeelight)

[![Documentation Status](https://readthedocs.org/projects/yeelight/badge/?version=stable)](http://yeelight.readthedocs.io/en/stable/?badge=stable)

`yeelight` is a simple Python library that allows you to control YeeLight WiFi RGB LED
bulbs through your LAN.

For a command-line utility that uses this library, see
[yeecli](https://gitlab.com/stavros/yeecli).

Installation
------------

There are many ways to install `yeelight`:

* With pip (preferred), run `pip install yeelight`.
* With setuptools, run `easy_install yeelight`.
* To install from source, download it from https://gitlab.com/stavros/python-yeelight
  and run `python setup.py install`.

Usage
-----

To use `yeelight`, first enable \"development mode\" on your bulb
through the YeeLight app. Then, just import the library into your
project like so:

```ipython
>>> from yeelight import Bulb
```

Afterwards, instantiate a bulb:

```ipython
>>> bulb = Bulb("192.168.0.5")
>>> bulb.turn_on()
```

That's it!

Refer to the rest of [the documentation](https://yeelight.readthedocs.io/en/stable/) for
more details.

The library also contains a (currently undocumented) asyncio interface.

Supported Devices
-----------------

See [the documentation](https://yeelight.readthedocs.io/en/stable/devices.html) for a list of supported devices.

Contributing
------------

If you'd like to contribute to the code, thank you! To install the various libraries
required, run (preferably in a virtualenv):

```bash
$ pip install -Ur requirements_dev.txt
```

In order for your MR to pass CI, it needs to be checked by various
utilities, which are managed by [pre-commit]{.title-ref}.
[pre-commit]{.title-ref} will be installed by the above command, but you
also need to install the pre-commit hook:

```bash
$ pre-commit install
```

The hook will run on commit. To run it manually (e.g. if you\'ve already
committed but forgot to run it, just run):

```bash
$ pre-commit run -a
```

Thanks again!

License
-------

`yeelight` is distributed under the BSD license.
