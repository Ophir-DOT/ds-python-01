"""Thin async client over Salesforce REST/Tooling + a tiny SOAP wrapper for Metadata.

REST/Tooling go over httpx so we can issue requests concurrently.
The Metadata API is SOAP-only; we hand-craft envelopes in `soap.py` and wrap the
sync POST calls in `asyncio.to_thread` so they compose with the async pipeline.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .auth import OrgCredentials
from .soap import MetadataSoapClient


class SalesforceClient:
    def __init__(self, creds: OrgCredentials) -> None:
        self._creds = creds
        self._http = httpx.AsyncClient(
            base_url=creds.instance_url,
            headers={
                "Authorization": f"Bearer {creds.access_token}",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(60.0, connect=10.0),
            http2=True,
        )
        self._soap = MetadataSoapClient(creds)

    @property
    def creds(self) -> OrgCredentials:
        return self._creds

    async def aclose(self) -> None:
        await self._http.aclose()

    # ---- REST / Tooling ---------------------------------------------------

    async def rest_get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        response = await self._http.get(path, params=params)
        response.raise_for_status()
        return response.json()

    async def describe(self, object_api_name: str) -> dict[str, Any]:
        version = self._creds.api_version
        return await self.rest_get(f"/services/data/v{version}/sobjects/{object_api_name}/describe")

    async def tooling_query(self, soql: str) -> dict[str, Any]:
        version = self._creds.api_version
        return await self.rest_get(
            f"/services/data/v{version}/tooling/query",
            params={"q": soql},
        )

    async def query(self, soql: str) -> dict[str, Any]:
        version = self._creds.api_version
        return await self.rest_get(
            f"/services/data/v{version}/query",
            params={"q": soql},
        )

    async def query_all(self, soql: str) -> list[dict[str, Any]]:
        """Run a SOQL query and follow `nextRecordsUrl` until all rows are read.

        Salesforce caps single-page query responses at 2000 records; for things
        like FieldPermissions filtered by ParentId we routinely exceed that.
        """
        result = await self.query(soql)
        records: list[dict[str, Any]] = list(result.get("records", []))
        next_url = result.get("nextRecordsUrl")
        while next_url:
            result = await self.rest_get(next_url)
            records.extend(result.get("records", []))
            next_url = result.get("nextRecordsUrl")
        return records

    # ---- Metadata API (SOAP, sync wrapped in a thread) --------------------

    async def read_metadata(self, type_name: str, full_names: list[str]) -> list[dict[str, Any]]:
        """Metadata API readMetadata, batched at the 10-record Salesforce cap.

        Multiple batches are issued concurrently (each batch in its own thread).
        """
        if not full_names:
            return []
        batches = [full_names[i : i + 10] for i in range(0, len(full_names), 10)]

        async def _one_batch(batch: list[str]) -> list[dict[str, Any]]:
            return await asyncio.to_thread(self._soap.read_metadata, type_name, batch)

        results = await asyncio.gather(*[_one_batch(b) for b in batches])
        flat: list[dict[str, Any]] = []
        for r in results:
            flat.extend(r)
        return flat

    async def list_metadata(self, type_name: str, folder: str | None = None) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._soap.list_metadata, type_name, folder)
