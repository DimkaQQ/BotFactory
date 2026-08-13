"""aiohttp session for aiogram, forced to IPv4.

Docker's default bridge network has no IPv6 route inside the container's
network namespace. `api.telegram.org` resolves to both an A and an AAAA
record, and aiohttp's happy-eyeballs connector tries the IPv6 address —
which fails instantly with "Network is unreachable" instead of falling
back cleanly, taking the whole request down with it. Forcing the
connector to AF_INET sidesteps that entirely.
"""

import socket
from typing import Any

from aiogram.client.session.aiohttp import AiohttpSession


class Ipv4AiohttpSession(AiohttpSession):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._connector_init["family"] = socket.AF_INET
