"""Clients for the services a run drives or watches: TEI, Ollama and the Docker Engine API."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx

TEI_TIMEOUT = httpx.Timeout(120.0, connect=5.0)
"""Reranking 20 long chunks on a small CPU can take tens of seconds."""


class Tei:
    """One Text Embeddings Inference container, serving one model (ADR-0028)."""

    def __init__(self, client: httpx.AsyncClient, url: str) -> None:
        self._client = client
        self._url = url.rstrip("/")

    async def info(self) -> dict[str, Any]:
        return await self._call("GET", "/info")  # type: ignore[no-any-return]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        body = {"inputs": list(texts), "normalize": True, "truncate": True}
        return await self._call("POST", "/embed", body)  # type: ignore[no-any-return]

    async def rerank(self, query: str, texts: Sequence[str]) -> list[tuple[int, float]]:
        """(index into `texts`, score), best first."""
        body = {"query": query, "texts": list(texts), "truncate": True}
        ranked = await self._call("POST", "/rerank", body)
        pairs = [(int(item["index"]), float(item["score"])) for item in ranked]
        return sorted(pairs, key=lambda pair: -pair[1])

    async def _call(self, method: str, path: str, body: object = None) -> Any:
        response = await self._client.request(
            method, self._url + path, json=body, timeout=TEI_TIMEOUT
        )
        response.raise_for_status()
        return response.json()


async def ollama_info(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    """Ollama's version, and the models it has loaded with their memory and context size."""
    url = url.rstrip("/")
    version = (await client.get(f"{url}/api/version", timeout=10)).json()
    loaded = (await client.get(f"{url}/api/ps", timeout=10)).json()
    return {"version": version.get("version"), "loaded": loaded.get("models", [])}


@dataclass(frozen=True)
class Container:
    id: str
    name: str
    """The Compose service, or the container's own name for one outside the stack."""


class Docker:
    """Read-only calls to the Docker Engine API, over its socket."""

    def __init__(self, socket: str = "/var/run/docker.sock") -> None:
        self._client = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(uds=socket), base_url="http://docker", timeout=10
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def info(self) -> dict[str, Any]:
        """The Docker host: CPUs, memory, architecture. On a Mac, Docker Desktop's VM."""
        return await self._get("/info")  # type: ignore[no-any-return]

    async def containers(self, project: str, extra: Sequence[str] = ()) -> list[Container]:
        """The running containers of a Compose project, plus others named in `extra`."""
        filters = json.dumps({"label": [f"com.docker.compose.project={project}"]})
        found = [
            Container(item["Id"], item["Labels"]["com.docker.compose.service"])
            for item in await self._get("/containers/json", params={"filters": filters})
        ]
        if extra:
            for item in await self._get("/containers/json"):
                names = [name.lstrip("/") for name in item["Names"]]
                found += [Container(item["Id"], name) for name in names if name in extra]
        return sorted(found, key=lambda container: container.name)

    async def environment(self, container: Container) -> dict[str, str]:
        details = await self._get(f"/containers/{container.id}/json")
        pairs = (entry.partition("=") for entry in details["Config"]["Env"] or [])
        return {name: value for name, _, value in pairs}

    async def stats(self, container: Container) -> dict[str, Any]:
        """One sample, without waiting for the API's second CPU reading."""
        path = f"/containers/{container.id}/stats"
        return await self._get(path, params={"stream": "false", "one-shot": "true"})  # type: ignore[no-any-return]

    async def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()
