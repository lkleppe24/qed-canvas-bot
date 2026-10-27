"""Minimal async Canvas LMS API client (student-token friendly)."""

from __future__ import annotations

import re
from typing import Any

import aiohttp

_NEXT_LINK = re.compile(r'<([^>]+)>;\s*rel="next"')


class CanvasError(Exception):
    pass


class CanvasClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "CanvasClient":
        self._session = aiohttp.ClientSession(
            headers=self._headers, timeout=aiohttp.ClientTimeout(total=30)
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._session:
            await self._session.close()

    async def _get_all(self, path: str, params: dict | list | None = None) -> list[dict]:
        """GET a paginated Canvas endpoint and return every item across pages."""
        assert self._session, "use 'async with CanvasClient(...)'"
        url: str | None = f"{self.base_url}/api/v1{path}"
        items: list[dict] = []
        first = True
        while url:
            async with self._session.get(url, params=params if first else None) as resp:
                if resp.status == 401:
                    raise CanvasError("Canvas rejected the token (401). Check CANVAS_TOKEN.")
                if resp.status >= 400:
                    body = await resp.text()
                    raise CanvasError(f"Canvas {resp.status} on {url}: {body[:200]}")
                data = await resp.json()
                items.extend(data if isinstance(data, list) else [data])
                match = _NEXT_LINK.search(resp.headers.get("Link", ""))
                url = match.group(1) if match else None
                first = False
        return items

    async def active_courses(self) -> list[dict]:
        return await self._get_all(
            "/courses", {"enrollment_state": "active", "per_page": 100}
        )

    async def assignments_with_submission(self, course_id: int | str) -> list[dict]:
        """All assignments in a course, each with *your* submission attached.

        For group assignments, Canvas copies the group's submission onto every
        member, so your own submission flips to 'submitted' when anyone in the
        group turns it in.
        """
        params = [("include[]", "submission"), ("per_page", "100")]
        return await self._get_all(f"/courses/{course_id}/assignments", params)
