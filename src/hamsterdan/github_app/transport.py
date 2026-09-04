"""Bounded GitHub authority and effect adapters for PR readiness.

This module deliberately contains provider values, not workflow/net values.  It
is safe to import: credentials are supplied explicitly and no I/O occurs until
an operation is called.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any, cast
from urllib.parse import urlsplit

import httpx
from githubkit import GitHub
from githubkit.exception import GitHubException

API_HOST = "api.github.com"
MAX_BODY_BYTES = 1_048_576
MAX_REQUEST_BYTES = 65_536
MAX_PAGES = 20
_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
_REF = re.compile(r"refs/heads/[A-Za-z0-9][A-Za-z0-9._/-]{0,254}\Z")
_METHODS = frozenset({"GET", "POST", "PATCH"})


from .models import GitHubBoundaryError, Transport, WireResponse


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class GitHubKitTransport:
    """Bounded fixed-origin gateway over one installation-authenticated client."""

    def __init__(self, client: GitHub):
        self._client = client

    def __repr__(self) -> str:
        return f"{type(self).__name__}(origin='https://{API_HOST}', credential=<owned-by-githubkit>)"

    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> WireResponse:
        if method not in _METHODS or not path.startswith("/") or path.startswith("//") or urlsplit(path).netloc:
            raise GitHubBoundaryError("GitHub request is outside the admitted origin or methods")
        if method == "GET" and body is not None:
            raise GitHubBoundaryError("GitHub GET request cannot contain a body")
        try:
            encoded = None if body is None else json.dumps(dict(body), allow_nan=False, separators=(",", ":")).encode()
        except TypeError, ValueError:
            raise GitHubBoundaryError("GitHub request body is not finite JSON") from None
        if encoded is not None and len(encoded) > MAX_REQUEST_BYTES:
            raise GitHubBoundaryError("GitHub request body exceeds its bound")
        try:
            with self._client.get_sync_client() as client:
                request = client.build_request(method, path, json=None if encoded is None else json.loads(encoded))
                with self._client.config.throttler.acquire(request):
                    raw_response = client.send(request, stream=True)
                try:
                    if 300 <= raw_response.status_code < 400:
                        raise GitHubBoundaryError("GitHub returned an unadmitted redirect")
                    raw = self._read(raw_response.iter_bytes(), MAX_BODY_BYTES)
                    value = None if not raw else json.loads(raw)
                    return WireResponse(raw_response.status_code, value, _next(raw_response.headers.get("link")))
                finally:
                    raw_response.close()
        except GitHubBoundaryError:
            raise
        except (
            GitHubException,
            httpx.HTTPError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            OSError,
            RuntimeError,
            ValueError,
        ) as error:
            raise GitHubBoundaryError(
                "GitHub request failed without a proven outcome",
                provider_detail=_transport_failure_detail(error),
            ) from None

    @staticmethod
    def _read(chunks: Iterable[bytes], limit: int) -> bytes:
        value = bytearray()
        for chunk in chunks:
            value.extend(chunk)
            if len(value) > limit:
                raise GitHubBoundaryError("GitHub response exceeds its bound")
        return bytes(value)

    def download(self, path: str, limit: int = MAX_BODY_BYTES) -> bytes:
        if limit <= 0 or not path.startswith("/") or path.startswith("//") or urlsplit(path).netloc:
            raise GitHubBoundaryError("GitHub download is outside the admitted origin or bound")
        try:
            with self._client.get_sync_client() as client:
                request = client.build_request("GET", path)
                with self._client.config.throttler.acquire(request):
                    raw_response = client.send(request, stream=True)
                try:
                    if raw_response.status_code != 200:
                        raise GitHubBoundaryError("GitHub download did not succeed")
                    return self._read(raw_response.iter_bytes(), limit)
                finally:
                    raw_response.close()
        except GitHubBoundaryError:
            raise
        except (GitHubException, httpx.HTTPError) as error:
            raise GitHubBoundaryError(
                "GitHub download failed without a proven outcome",
                provider_detail=_transport_failure_detail(error),
            ) from None

    def pages(self, path: str) -> tuple[dict[str, Any], ...]:
        values: list[dict[str, Any]] = []
        seen: set[str] = set()
        current: str | None = path
        while current is not None:
            if current in seen or len(seen) >= MAX_PAGES:
                raise GitHubBoundaryError("GitHub pagination is cyclic or exceeds its bound")
            seen.add(current)
            response = self.request("GET", current)
            if (
                response.status != 200
                or not isinstance(response.body, list)
                or not all(isinstance(v, dict) for v in response.body)
            ):
                raise GitHubBoundaryError("GitHub paginated response is not a successful object list")
            values.extend(cast(list[dict[str, Any]], response.body))
            current = response.next_path
        return tuple(values)


def _transport_failure_detail(error: Exception) -> str:
    if isinstance(error, httpx.TransportError):
        return "http_transport"
    if isinstance(error, GitHubException):
        return "github_exception"
    if isinstance(error, UnicodeDecodeError):
        return "response_encoding"
    if isinstance(error, json.JSONDecodeError):
        return "response_json"
    if isinstance(error, OSError):
        return "os_error"
    if isinstance(error, RuntimeError):
        return "runtime_error"
    return "value_error"


class GitHubGraphQL:
    """Bounded GraphQL authority over the same fixed-origin credential."""

    def __init__(self, transport: Transport):
        self.transport = transport

    def review_threads(self, owner: str, repository: str, pr_number: int) -> tuple[Mapping[str, Any], ...]:
        query = """
        query($owner:String!,$repository:String!,$number:Int!,$after:String) {
          repository(owner:$owner,name:$repository) {
            pullRequest(number:$number) {
              reviewThreads(first:100,after:$after) {
                nodes { id isResolved comments(first:1) { nodes { viewerDidAuthor body } } }
                pageInfo { hasNextPage endCursor }
              }
            }
          }
        }
        """
        values: list[Mapping[str, Any]] = []
        cursor: str | None = None
        for _ in range(MAX_PAGES):
            response = self.transport.request(
                "POST",
                "/graphql",
                {
                    "query": query,
                    "variables": {"owner": owner, "repository": repository, "number": pr_number, "after": cursor},
                },
            )
            if response.status != 200 or not isinstance(response.body, dict) or response.body.get("errors"):
                raise GitHubBoundaryError("GitHub review-thread evidence is unavailable")
            try:
                body = cast(dict[str, Any], response.body)
                threads = body["data"]["repository"]["pullRequest"]["reviewThreads"]
                nodes, page = threads["nodes"], threads["pageInfo"]
                if (
                    not isinstance(nodes, list)
                    or not all(
                        isinstance(node, dict)
                        and isinstance(node.get("id"), str)
                        and type(node.get("isResolved")) is bool
                        for node in nodes
                    )
                    or not isinstance(page, dict)
                    or type(page.get("hasNextPage")) is not bool
                ):
                    raise TypeError
            except KeyError, TypeError:
                raise GitHubBoundaryError("GitHub review-thread evidence is malformed") from None
            values.extend(nodes)
            if not page["hasNextPage"]:
                return tuple(values)
            cursor = page.get("endCursor")
            if not isinstance(cursor, str) or not cursor:
                raise GitHubBoundaryError("GitHub review-thread pagination is malformed")
        raise GitHubBoundaryError("GitHub review-thread pagination exceeds its bound")

    def resolve_review_thread(self, thread_id: str) -> None:
        mutation = """
        mutation($thread:ID!) {
          resolveReviewThread(input:{threadId:$thread}) { thread { id isResolved } }
        }
        """
        response = self.transport.request("POST", "/graphql", {"query": mutation, "variables": {"thread": thread_id}})
        if response.status != 200 or not isinstance(response.body, dict) or response.body.get("errors"):
            raise GitHubBoundaryError("GitHub did not prove review-thread resolution")
        try:
            body = cast(dict[str, Any], response.body)
            thread = body["data"]["resolveReviewThread"]["thread"]
            if thread.get("id") != thread_id or thread.get("isResolved") is not True:
                raise TypeError
        except KeyError, TypeError:
            raise GitHubBoundaryError("GitHub did not prove review-thread resolution") from None

    def compare_and_swap_ref(self, repository: str, ref: str, expected_head: str, commit: str) -> None:
        owner, separator, name = repository.partition("/")
        if (
            not separator
            or not owner
            or not name
            or "/" in name
            or not _REF.fullmatch(ref)
            or ".." in ref
            or "@{" in ref
            or not _SHA.fullmatch(expected_head)
            or not _SHA.fullmatch(commit)
        ):
            raise GitHubBoundaryError("GitHub ref compare-and-swap input is malformed")
        repository_query = """
        query($owner:String!,$repository:String!) {
          repository(owner:$owner,name:$repository) { id }
        }
        """
        response = self.transport.request(
            "POST",
            "/graphql",
            {"query": repository_query, "variables": {"owner": owner, "repository": name}},
        )
        if response.status != 200 or not isinstance(response.body, dict) or response.body.get("errors"):
            raise GitHubBoundaryError("GitHub repository identity is unavailable for ref compare-and-swap")
        try:
            body = cast(dict[str, Any], response.body)
            repository_id = body["data"]["repository"]["id"]
            if not isinstance(repository_id, str):
                raise TypeError
        except KeyError, TypeError:
            raise GitHubBoundaryError("GitHub repository identity is unavailable for ref compare-and-swap") from None

        client_id = _digest({"repository": repository, "ref": ref, "expected_head": expected_head, "commit": commit})
        mutation = """
        mutation($input:UpdateRefsInput!) {
          updateRefs(input:$input) { clientMutationId }
        }
        """
        response = self.transport.request(
            "POST",
            "/graphql",
            {
                "query": mutation,
                "variables": {
                    "input": {
                        "repositoryId": repository_id,
                        "refUpdates": [
                            {
                                "name": ref,
                                "beforeOid": expected_head,
                                "afterOid": commit,
                                "force": False,
                            }
                        ],
                        "clientMutationId": client_id,
                    }
                },
            },
        )
        if response.status != 200 or not isinstance(response.body, dict) or response.body.get("errors"):
            raise GitHubBoundaryError("GitHub rejected or did not prove the exact ref compare-and-swap")
        try:
            body = cast(dict[str, Any], response.body)
            observed = body["data"]["updateRefs"]["clientMutationId"]
            if observed != client_id:
                raise TypeError
        except KeyError, TypeError:
            raise GitHubBoundaryError("GitHub rejected or did not prove the exact ref compare-and-swap") from None


def _next(link: str | None) -> str | None:
    if not link:
        return None
    found: str | None = None
    for part in link.split(","):
        target, *parameters = part.strip().split(";")
        if any(parameter.strip() == 'rel="next"' for parameter in parameters):
            target = target.strip()
            if found is not None or len(target) < 3 or not target.startswith("<") or not target.endswith(">"):
                raise GitHubBoundaryError("GitHub pagination evidence is malformed or ambiguous")
            try:
                parsed = urlsplit(target[1:-1])
                invalid = (
                    parsed.scheme != "https"
                    or parsed.hostname != API_HOST
                    or parsed.port is not None
                    or parsed.username is not None
                    or parsed.password is not None
                    or bool(parsed.fragment)
                    or not parsed.path.startswith("/")
                )
            except ValueError:
                invalid = True
            if invalid:
                raise GitHubBoundaryError("GitHub pagination escaped the admitted origin")
            found = parsed.path + (("?" + parsed.query) if parsed.query else "")
    return found
