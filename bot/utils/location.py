"""Optional locality verification; not proof of physical activity."""

import asyncio
import os
import time

from geopy.adapters import AioHTTPAdapter
from geopy.exc import GeocoderServiceError
from geopy.geocoders import Nominatim

from classes.database import Database


class LocationLookupError(ValueError):
    pass


def local_label(address: dict) -> str | None:
    """Return only neighborhood/city/country, never an exact street address."""
    neighborhood = next(
        (address[key] for key in ("suburb", "neighbourhood", "quarter") if address.get(key)), None
    )
    city = next(
        (address[key] for key in ("city", "town", "village", "municipality", "county", "state")
         if address.get(key)), None
    )
    country = address.get("country")
    unique = list(dict.fromkeys(x for x in (neighborhood, city, country) if x))
    return ", ".join(unique)[:120] if unique else None


class LocationResolver:
    """Single-process rate limiting and persistent SQLite cache for Nominatim.

    Public Nominatim usage requires an identifying agent, <= 1 request/second,
    local caching and OpenStreetMap attribution. Do not use for bulk queries.
    """

    def __init__(self, db: Database):
        self.db = db
        self.user_agent = os.getenv("GEOCODER_USER_AGENT", "").strip()
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def resolve(self, query: str | None) -> str | None:
        if not query or not query.strip():
            return None
        query = " ".join(query.strip().split())
        if len(query) > 100:
            raise LocationLookupError("Use a city or neighborhood (100 characters maximum).")
        if any(char.isdigit() for char in query):
            raise LocationLookupError("Use a city/neighborhood and country, not a street address.")
        if not self.user_agent:
            raise LocationLookupError(
                "Location lookup is not enabled. Ask the owner to set GEOCODER_USER_AGENT, "
                "or leave location blank."
            )

        key = query.casefold()
        cached, result = await self.db.get_cached_place(key)
        if cached:
            if result is None:
                raise LocationLookupError("Place not found. Try adding its city and country.")
            return result

        async with self._lock:
            cached, result = await self.db.get_cached_place(key)
            if cached:
                if result is None:
                    raise LocationLookupError("Place not found. Try adding its city and country.")
                return result

            # One process, one geocoder, one request at a time.
            pause = 1.1 - (time.monotonic() - self._last_call)
            if pause > 0:
                await asyncio.sleep(pause)
            self._last_call = time.monotonic()

            try:
                async with Nominatim(
                    user_agent=self.user_agent,
                    adapter_factory=AioHTTPAdapter,
                    timeout=7,
                ) as geo:
                    place = await geo.geocode(query, addressdetails=True, exactly_one=True)
            except GeocoderServiceError as exc:
                raise LocationLookupError(
                    "Place lookup is temporarily unavailable. Try again without location."
                ) from exc

            label = local_label(place.raw.get("address", {})) if place else None
            await self.db.cache_place(key, label)
            if not label:
                raise LocationLookupError("Place not found. Try adding its city and country.")
            return label
