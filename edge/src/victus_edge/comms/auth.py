"""Bearer token provider for Foundry HTTP calls.

Two modes selected at construction time:

- ``STATIC``: a long-lived personal API token from env. Phase 1.0 default;
  zero ceremony for hackathon bring-up.
- ``OAUTH``: client_credentials grant against Foundry's OAuth token endpoint.
  Caches the access token and refreshes ~5 min before expiry. Refresh path is
  guarded by an asyncio.Lock so concurrent callers don't trigger duplicate
  token fetches under a 401 storm.

Both modes expose the same coroutine: ``await provider.token() -> str``.
"""

import asyncio
import time
from typing import Literal

import httpx


_REFRESH_SAFETY_S = 300  # refresh this many seconds before token expiry


class TokenProvider:
    def __init__(
        self,
        mode: Literal["STATIC", "OAUTH"],
        *,
        static_token: str | None = None,
        oauth_token_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self.mode = mode
        self._static_token = static_token
        self._oauth_token_url = oauth_token_url
        self._client_id = client_id
        self._client_secret = client_secret

        self._cached_token: str | None = None
        self._expires_at_epoch: float = 0.0
        self._lock = asyncio.Lock()

        if mode == "STATIC":
            if not static_token:
                raise ValueError("STATIC mode requires static_token")
        elif mode == "OAUTH":
            if not (oauth_token_url and client_id and client_secret):
                raise ValueError(
                    "OAUTH mode requires oauth_token_url, client_id, client_secret"
                )
        else:
            raise ValueError(f"unknown auth mode: {mode}")

    async def token(self) -> str:
        if self.mode == "STATIC":
            assert self._static_token is not None
            return self._static_token

        if self._cached_token and time.time() < self._expires_at_epoch - _REFRESH_SAFETY_S:
            return self._cached_token

        async with self._lock:
            if self._cached_token and time.time() < self._expires_at_epoch - _REFRESH_SAFETY_S:
                return self._cached_token
            await self._refresh_oauth()
            assert self._cached_token is not None
            return self._cached_token

    async def _refresh_oauth(self) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                self._oauth_token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            body = resp.json()

        self._cached_token = body["access_token"]
        self._expires_at_epoch = time.time() + float(body.get("expires_in", 3600))
