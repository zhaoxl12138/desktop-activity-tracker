"""Compatibility alias for the pre-DayLens package name."""

import daylens as _daylens
from daylens import *  # noqa: F401,F403

__path__ = _daylens.__path__
