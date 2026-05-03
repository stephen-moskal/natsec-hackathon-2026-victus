"""llama-server subprocess manager.

Spawns llama-server as a child process, polls /health until ready, and
gracefully shuts it down on context exit. Mirrors the flag set the deleted
entrypoint.sh used previously — main.py now owns this lifecycle so a single
process can coordinate the model server, webcam, and Foundry comms.

Subprocess stdout/stderr inherit the parent's file descriptors. llama-server
logs interleave naturally with the harness logs without us doing any piping.

Note on subprocess safety: we use asyncio.create_subprocess_exec (NOT the
_shell variant), which fork+exec's directly without a shell. Args are passed
as a list, so there is no command injection surface even though the binary
name and model paths are configurable.
"""

import asyncio

import structlog

from .http_client import LlamaCppClient


log = structlog.get_logger(__name__)


_DEFAULT_PORT = 8080
_DEFAULT_CTX = 2048
_DEFAULT_BATCH = 256
_DEFAULT_UBATCH = 256
_HEALTH_TIMEOUT_S = 90.0
_SHUTDOWN_GRACE_S = 5.0
_HEALTH_POLL_INTERVAL_S = 1.0


class LlamaServerError(RuntimeError):
    """llama-server failed to start, crashed during startup, or wouldn't stop."""


class LlamaServer:
    """Async context manager that owns a llama-server child process.

    Usage:

        async with LlamaServer(model_path, mmproj_path) as server:
            async with LlamaCppClient(server.base_url) as client:
                ...

    On exit: SIGTERM, wait `_SHUTDOWN_GRACE_S`, then SIGKILL if still alive.
    """

    def __init__(
        self,
        model_path: str,
        mmproj_path: str | None,
        port: int = _DEFAULT_PORT,
        ctx: int = _DEFAULT_CTX,
        batch: int = _DEFAULT_BATCH,
        ubatch: int = _DEFAULT_UBATCH,
        host: str = "0.0.0.0",
        binary: str = "llama-server",
    ) -> None:
        self._model_path = model_path
        self._mmproj_path = mmproj_path
        self._port = port
        self._ctx = ctx
        self._batch = batch
        self._ubatch = ubatch
        self._host = host
        self._binary = binary
        self._process: asyncio.subprocess.Process | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def _build_args(self) -> list[str]:
        args = [
            self._binary,
            "-m", self._model_path,
            "-ngl", "99",
            "-c", str(self._ctx),
            "-b", str(self._batch),
            "-ub", str(self._ubatch),
            "--parallel", "1",
            "--cache-ram", "0",
            "--host", self._host,
            "--port", str(self._port),
            "--jinja",
        ]
        if self._mmproj_path:
            args.extend(["--mmproj", self._mmproj_path])
        return args

    async def __aenter__(self) -> "LlamaServer":
        args = self._build_args()
        log.info("llama_server_starting", args=args)
        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
        )
        try:
            await self._wait_until_ready()
        except Exception:
            await self._terminate()
            raise
        log.info("llama_server_ready", base_url=self.base_url, pid=self._process.pid)
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self._terminate()

    async def _wait_until_ready(self) -> None:
        """Poll /health until 200 or timeout. Raise if subprocess exits early."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _HEALTH_TIMEOUT_S
        async with LlamaCppClient(self.base_url, timeout_s=2.0) as client:
            while True:
                if self._process is not None and self._process.returncode is not None:
                    raise LlamaServerError(
                        f"llama-server exited during startup "
                        f"(code={self._process.returncode})"
                    )
                if await client.health():
                    return
                if loop.time() > deadline:
                    raise LlamaServerError(
                        f"llama-server /health did not respond within {_HEALTH_TIMEOUT_S}s"
                    )
                await asyncio.sleep(_HEALTH_POLL_INTERVAL_S)

    async def _terminate(self) -> None:
        if self._process is None or self._process.returncode is not None:
            return
        pid = self._process.pid
        log.info("llama_server_terminating", pid=pid)
        try:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=_SHUTDOWN_GRACE_S)
            except asyncio.TimeoutError:
                log.warning("llama_server_kill_after_grace", pid=pid)
                self._process.kill()
                await self._process.wait()
        finally:
            log.info("llama_server_stopped", pid=pid, code=self._process.returncode)
