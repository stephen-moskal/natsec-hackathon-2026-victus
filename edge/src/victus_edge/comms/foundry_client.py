"""HTTP client for talking to Foundry.

Two responsibilities, both via standard Foundry REST APIs:

1. Outbound (telemetry): publish each envelope as a flat record to a streaming
   dataset using the Streams V2 ``publishRecords`` endpoint.
   ``POST /api/v2/highScale/streams/datasets/{datasetRid}/streams/master/publishRecords``

2. Inbound (commands): poll the Ontology Search Objects endpoint for Command
   objects matching ``device_id == this drone AND status == PENDING``.
   ``POST /api/v2/ontologies/{ontology}/objects/{commandObjectType}/search``

Auth: standard Foundry bearer token (TokenProvider). Token must hold
``api:streams-write`` (telemetry) and ``api:ontologies-read`` (commands).
"""

import json
from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .auth import TokenProvider
from .protocol import Envelope, ProtocolError, encode_telemetry, validate


log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class FoundryEndpoints:
    """Where to find the things this client talks to."""

    stack_url: str               # e.g. https://victus.usw-23.palantirfoundry.com
    telemetry_dataset_rid: str   # streaming dataset for raw_telemetry
    telemetry_view_rid: str | None  # streaming view RID; optional but recommended
    ontology: str                # ontology API name OR RID
    command_object_type: str     # API name of the command object type, e.g. "pzqmccug.command"


@dataclass(frozen=True)
class InvalidCommand:
    """A command row in Foundry that couldn't be decoded into a valid envelope.

    Surfaced from poll_commands so the caller can send a CommandAck { UNABLE }
    once and stop reprocessing the row on every poll.
    """

    message_id: str
    reason: str


class FoundryClient:
    def __init__(
        self,
        token_provider: TokenProvider,
        endpoints: FoundryEndpoints,
        drone_id: str,
        buffer_path: str,
        timeout_s: float = 10.0,
    ) -> None:
        self._token_provider = token_provider
        self._ep = endpoints
        self._drone_id = drone_id
        self._buffer_path = buffer_path
        self._timeout = timeout_s
        self._client: httpx.AsyncClient | None = None
        self._seen_command_ids: set[str] = set()

    async def __aenter__(self) -> "FoundryClient":
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *exc_info) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _auth_headers(self) -> dict[str, str]:
        token = await self._token_provider.token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    @staticmethod
    def _envelope_to_record(env: dict[str, Any]) -> dict[str, Any]:
        """Flatten a telemetry envelope into a record matching the streaming dataset schema."""
        payload = env["payload"]
        return {
            "protocol_version": env["protocol_version"],
            "message_id": env["message_id"],
            "issued_at": env["issued_at"],
            "sender": env["sender"],
            "kind": env["kind"],
            "event": payload.get("event", ""),
            "payload_json": json.dumps(payload),
        }

    def _object_to_envelope(self, obj: dict[str, Any]) -> Envelope:
        """Reconstruct a command Envelope from an ontology object record.

        Foundry auto-converts property IDs to camelCase API names at deploy
        time (e.g. message_id -> messageId, params_json -> paramsJson). The
        edge's wire envelope uses snake_case, so we translate at this boundary.
        """
        params: dict[str, Any]
        raw_params = obj.get("paramsJson") or obj.get("params_json") or "{}"
        try:
            params = json.loads(raw_params) if isinstance(raw_params, str) else dict(raw_params)
        except json.JSONDecodeError:
            params = {}
        env_dict = {
            "protocol_version": "0.3.0",
            "message_id": obj.get("messageId") or obj["message_id"],
            "issued_at": obj.get("issuedAt") or obj.get("issued_at") or "",
            "sender": "foundry-orchestrator",
            "kind": "command",
            "payload": {
                "drone_id": obj.get("deviceId") or obj["device_id"],
                "verb": obj["verb"],
                "priority": obj.get("priority", "ROUTINE"),
                "expires_at": obj.get("expiresAt") or obj.get("expires_at") or "",
                "params": params,
            },
        }
        validate(env_dict)
        return Envelope(**env_dict)

    async def post_telemetry(self, batch: list[dict[str, Any]]) -> None:
        """Publish a batch of telemetry envelopes to the streaming dataset."""
        assert self._client is not None, "use FoundryClient as async context manager"
        if not batch:
            return

        url = (
            f"{self._ep.stack_url}/api/v2/highScale/streams/datasets/"
            f"{self._ep.telemetry_dataset_rid}/streams/master/publishRecords"
        )
        body: dict[str, Any] = {
            "records": [self._envelope_to_record(env) for env in batch],
        }
        if self._ep.telemetry_view_rid:
            body["viewRid"] = self._ep.telemetry_view_rid

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=0.5, max=4),
                retry=retry_if_exception_type(
                    (httpx.TransportError, httpx.HTTPStatusError)
                ),
                reraise=True,
            ):
                with attempt:
                    resp = await self._client.post(
                        url, json=body, headers=await self._auth_headers()
                    )
                    if resp.status_code >= 500:
                        resp.raise_for_status()
                    if resp.status_code >= 400:
                        log.error(
                            "telemetry_publish_4xx",
                            status=resp.status_code,
                            body=resp.text[:500],
                            count=len(batch),
                        )
                        return
        except Exception as exc:
            log.error(
                "telemetry_publish_failed_buffering_pending",
                count=len(batch),
                error=str(exc),
            )
            # TODO Phase 1.1: append envelopes to JSONL buffer at self._buffer_path

    async def poll_commands(
        self, since_message_id: str | None
    ) -> tuple[list[Envelope], list["InvalidCommand"]]:
        """Search ontology for PENDING commands addressed to this drone.

        Returns a pair: (valid envelopes, invalid commands). Each invalid command
        carries the message_id and a human-readable reason; the caller is expected
        to send a ``CommandAck { result: UNABLE, reason: ... }`` for each so the
        operator-visible status can flip to REJECTED.

        Dedup is local: once a message_id has been seen — valid or invalid — it
        will not be returned again from this method (even if Foundry's status
        transform hasn't yet flipped it out of PENDING). The ``since_message_id``
        argument is accepted for symmetry with the older interface but is not
        strictly required.
        """
        assert self._client is not None, "use FoundryClient as async context manager"
        url = (
            f"{self._ep.stack_url}/api/v2/ontologies/{self._ep.ontology}/objects/"
            f"{self._ep.command_object_type}/search"
        )
        # Field names are camelCase API names assigned by Foundry's auto-converter.
        body = {
            "where": {
                "type": "and",
                "value": [
                    {"type": "eq", "field": "deviceId", "value": self._drone_id},
                    {"type": "eq", "field": "status", "value": "PENDING"},
                ],
            },
            "orderBy": {"fields": [{"field": "messageId", "direction": "asc"}]},
            "pageSize": 50,
        }
        try:
            resp = await self._client.post(
                url, json=body, headers=await self._auth_headers()
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("poll_commands_failed", error=str(exc))
            return [], []

        data = resp.json().get("data", [])
        envelopes: list[Envelope] = []
        invalid: list[InvalidCommand] = []
        for obj in data:
            mid = obj.get("messageId") or obj.get("message_id")
            if not mid or mid in self._seen_command_ids:
                continue
            try:
                env = self._object_to_envelope(obj)
            except (KeyError, ProtocolError) as exc:
                # Per policy: "Unparseable commands return UNABLE with reason
                # 'command unclear, say again'." We surface the schema reason to
                # the caller so they can ACK once and stop reprocessing.
                reason = str(exc) if isinstance(exc, ProtocolError) else f"missing field: {exc}"
                log.error("invalid_command_will_ack_unable", error=reason, message_id=mid)
                invalid.append(InvalidCommand(message_id=str(mid), reason=reason))
                self._seen_command_ids.add(mid)
                continue
            envelopes.append(env)
            self._seen_command_ids.add(mid)
        return envelopes, invalid

    async def ack_command(
        self, command_id: str, result: str, reason: str | None = None
    ) -> None:
        """Emit a CommandAck telemetry event for the given command."""
        fields: dict[str, Any] = {"command_id": command_id, "result": result}
        if reason is not None:
            fields["reason"] = reason
        envelope = encode_telemetry(
            sender=f"drone-{self._drone_id}",
            event="CommandAck",
            fields=fields,
        )
        await self.post_telemetry([envelope])

    async def drain_buffer(self) -> None:
        """Flush any buffered telemetry from disk in original order. Phase 1.1."""
        return None
