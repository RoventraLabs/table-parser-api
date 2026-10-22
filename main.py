from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl

MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
MAX_TABLES = 20
MAX_ROWS_PER_TABLE = 5_000
MAX_COLUMNS_PER_TABLE = 100
MAX_TOTAL_CELLS = 100_000
REQUEST_TIMEOUT = (3, 10)

app = FastAPI(
    title="HTML Table to JSON Parser for AI Agents",
    description=(
        "Extracts tables from publicly accessible HTML webpages and converts "
        "them to JSON. No API key or paid AI service is required."
    ),
    version="1.2.0",
)


class TableExtractRequest(BaseModel):
    url: HttpUrl


class TableExtractResponse(BaseModel):
    url: str
    tables_found: int
    tables: list[list[dict[str, Any]]]


@app.get("/", tags=["Service"])
def service_info() -> dict[str, Any]:
    """Provide a simple entry point for people and API-discovery tools."""
    return {
        "name": "HTML Table to JSON Parser for AI Agents",
        "version": app.version,
        "status": "available",
        "authentication": "none",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "health": "/health",
        "extract_endpoint": {
            "method": "POST",
            "path": "/api/v1/extract-tables",
            "content_type": "application/json",
            "body": {"url": "https://www.w3schools.com/html/html_tables.asp"},
        },
        "limits": {
            "max_html_bytes": MAX_HTML_BYTES,
            "max_redirects": MAX_REDIRECTS,
            "max_tables": MAX_TABLES,
            "max_rows_per_table": MAX_ROWS_PER_TABLE,
            "max_columns_per_table": MAX_COLUMNS_PER_TABLE,
            "max_total_cells": MAX_TOTAL_CELLS,
        },
    }


@app.get("/health", tags=["Service"])
def health_check() -> dict[str, str]:
    """Lightweight health check for hosting platforms and uptime monitors."""
    return {"status": "ok"}


def validate_public_url(url: str) -> None:
    """Reject non-public destinations to reduce SSRF risk; validate every redirect."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Only HTTP and HTTPS URLs are supported.")
        if not parsed.hostname:
            raise ValueError("The URL must include a hostname.")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("URLs containing credentials are not allowed.")

        port = parsed.port
        if port is not None and port not in {80, 443}:
            raise ValueError("Only ports 80 and 443 are allowed.")

        hostname = parsed.hostname.lower().rstrip(".")
        blocked_suffixes = (
            ".localhost",
            ".local",
            ".internal",
            ".home.arpa",
            ".lan",
        )
        if hostname == "localhost" or hostname.endswith(blocked_suffixes):
            raise ValueError("Private and local hostnames are not allowed.")

        try:
            addresses = {ipaddress.ip_address(hostname)}
        except ValueError:
            try:
                records = socket.getaddrinfo(
                    hostname,
                    port or (443 if parsed.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
            except socket.gaierror as exc:
                raise ValueError("The hostname could not be resolved.") from exc
            addresses = {ipaddress.ip_address(record[4][0]) for record in records}

        if not addresses or any(not address.is_global for address in addresses):
            raise ValueError("The URL must resolve only to public IP addresses.")
    except (ValueError, UnicodeError) as exc:
        raise ValueError(
            "URL rejected: use a public HTTP/HTTPS address on port 80 or 443."
        ) from exc


def fetch_public_html(start_url: str) -> str:
    current_url = start_url
    headers = {
        "User-Agent": "RoventraLabs-TableParser/1.2",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
    }

    for redirect_count in range(MAX_REDIRECTS + 1):
        try:
            validate_public_url(current_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        try:
            with requests.get(
                current_url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
                stream=True,
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if not location:
                        raise HTTPException(
                            status_code=502,
                            detail="The source returned an invalid redirect.",
                        )
                    if redirect_count >= MAX_REDIRECTS:
                        raise HTTPException(
                            status_code=502,
                            detail="The source exceeded the redirect limit.",
                        )
                    current_url = urljoin(current_url, location)
                    continue

                response.raise_for_status()
                declared_size = response.headers.get("Content-Length")
                if declared_size:
                    try:
                        if int(declared_size) > MAX_HTML_BYTES:
                            raise HTTPException(
                                status_code=413,
                                detail="The source page is larger than the 2 MiB limit.",
                            )
                    except ValueError:
                        pass

                chunks: list[bytes] = []
                total_size = 0
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    total_size += len(chunk)
                    if total_size > MAX_HTML_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail="The source page is larger than the 2 MiB limit.",
                        )
                    chunks.append(chunk)

                encoding = response.encoding or "utf-8"
                return b"".join(chunks).decode(encoding, errors="replace")

        except HTTPException:
            raise
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail="Could not fetch the source page. Check the URL and try again.",
            ) from exc

    raise HTTPException(status_code=502, detail="The source exceeded the redirect limit.")


@app.post(
    "/api/v1/extract-tables",
    response_model=TableExtractResponse,
    tags=["Extraction"],
    summary="Extract HTML tables from a public webpage",
)
def extract_tables(request: TableExtractRequest) -> TableExtractResponse:
    """Fetch a public webpage and return its HTML tables as JSON records."""
    html = fetch_public_html(str(request.url))

    try:
        dataframes = pd.read_html(html)
    except ValueError:
        # pandas raises ValueError when no HTML tables are present.
        return TableExtractResponse(url=str(request.url), tables_found=0, tables=[])

    if len(dataframes) > MAX_TABLES:
        raise HTTPException(
            status_code=413,
            detail=f"The page contains more than {MAX_TABLES} tables.",
        )

    extracted_tables: list[list[dict[str, Any]]] = []
    total_cells = 0

    for dataframe in dataframes:
        row_count, column_count = dataframe.shape
        if row_count > MAX_ROWS_PER_TABLE or column_count > MAX_COLUMNS_PER_TABLE:
            raise HTTPException(
                status_code=413,
                detail="A table exceeds the supported row or column limit.",
            )

        total_cells += row_count * column_count
        if total_cells > MAX_TOTAL_CELLS:
            raise HTTPException(
                status_code=413,
                detail="The page contains too much table data to process safely.",
            )

        dataframe.columns = [str(column) for column in dataframe.columns]
        cleaned_dataframe = dataframe.fillna("")
        extracted_tables.append(cleaned_dataframe.to_dict(orient="records"))

    return TableExtractResponse(
        url=str(request.url),
        tables_found=len(extracted_tables),
        tables=extracted_tables,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000)
