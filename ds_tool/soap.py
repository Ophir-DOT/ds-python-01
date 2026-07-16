"""Minimal Salesforce Metadata API SOAP client.

We only need two operations — `readMetadata` and `listMetadata` — and the
Metadata WSDL is browser-auth-only (it redirects bearer-token requests to a
login page). So instead of pulling in zeep + WSDL parsing, we build the SOAP
envelopes by hand and parse responses with stdlib xml.etree.

The dict shape returned here intentionally matches what `metadata/profiles.py`
expects from a normalized Metadata API record (camelCase keys, repeated child
elements collapsed into lists).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import httpx

from .auth import OrgCredentials

NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
NS_META = "http://soap.sforce.com/2006/04/metadata"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
ET.register_namespace("", NS_META)
ET.register_namespace("soapenv", NS_SOAP)
ET.register_namespace("xsi", NS_XSI)


def _envelope(session_id: str, body_xml: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<soapenv:Envelope xmlns:soapenv="{NS_SOAP}" xmlns="{NS_META}">'
        "<soapenv:Header>"
        f"<SessionHeader><sessionId>{escape(session_id)}</sessionId></SessionHeader>"
        "</soapenv:Header>"
        f"<soapenv:Body>{body_xml}</soapenv:Body>"
        "</soapenv:Envelope>"
    )


def _read_metadata_body(type_name: str, full_names: list[str]) -> str:
    names_xml = "".join(f"<fullNames>{escape(n)}</fullNames>" for n in full_names)
    return f"<readMetadata><type>{escape(type_name)}</type>{names_xml}</readMetadata>"


def _list_metadata_body(type_name: str, folder: str | None, api_version: str) -> str:
    query = f"<queries><type>{escape(type_name)}</type>"
    if folder:
        query += f"<folder>{escape(folder)}</folder>"
    query += "</queries>"
    return f"<listMetadata>{query}<asOfVersion>{escape(api_version)}</asOfVersion></listMetadata>"


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _element_to_value(element: ET.Element) -> Any:
    """Convert a SOAP response element into a string / dict / list-of-dicts."""
    children = list(element)
    if not children:
        return (element.text or "").strip()

    result: dict[str, Any] = {}
    for child in children:
        key = _strip_ns(child.tag)
        value = _element_to_value(child)
        if key in result:
            existing = result[key]
            if isinstance(existing, list):
                existing.append(value)
            else:
                result[key] = [existing, value]
        else:
            result[key] = value
    return result


def _parse_records(response_xml: bytes, operation: str) -> list[dict[str, Any]]:
    """Extract records from a SOAP response, handling both API shapes.

    readMetadata returns one <result> with multiple <records> children, some
    marked xsi:nil="true" for names that didn't match. listMetadata returns
    multiple sibling <result> elements, each itself a record.
    """
    root = ET.fromstring(response_xml)
    body = root.find(f"{{{NS_SOAP}}}Body")
    if body is None:
        return []
    op_response = body.find(f"{{{NS_META}}}{operation}Response")
    if op_response is None:
        # Surface SOAP faults clearly
        fault = body.find(f"{{{NS_SOAP}}}Fault")
        if fault is not None:
            faultstring = fault.findtext("faultstring") or "Unknown SOAP fault"
            raise MetadataSoapError(faultstring.strip())
        return []

    records: list[dict[str, Any]] = []
    nil_attr = f"{{{NS_XSI}}}nil"
    for result_el in op_response.findall(f"{{{NS_META}}}result"):
        record_children = result_el.findall(f"{{{NS_META}}}records")
        if record_children:
            # readMetadata: one <result> with many <records> children
            for record_el in record_children:
                if record_el.get(nil_attr) == "true":
                    continue
                value = _element_to_value(record_el)
                if isinstance(value, dict):
                    records.append(value)
        else:
            # listMetadata: each <result> is itself a record
            value = _element_to_value(result_el)
            if isinstance(value, dict):
                records.append(value)
    return records


class MetadataSoapError(RuntimeError):
    pass


class MetadataSoapClient:
    def __init__(self, creds: OrgCredentials) -> None:
        self._creds = creds
        self._endpoint = (
            f"{creds.instance_url}/services/Soap/m/{creds.api_version}"
        )

    def _post(self, body_xml: str, soap_action: str) -> bytes:
        envelope = _envelope(self._creds.access_token, body_xml)
        response = httpx.post(
            self._endpoint,
            content=envelope.encode("utf-8"),
            headers={
                "Content-Type": 'text/xml; charset=UTF-8',
                "SOAPAction": soap_action,
                "Accept": "text/xml",
            },
            timeout=httpx.Timeout(120.0, connect=15.0),
        )
        debug_dir = os.environ.get("DS_TOOL_DEBUG_SOAP")
        if debug_dir:
            outdir = Path(debug_dir)
            outdir.mkdir(parents=True, exist_ok=True)
            stamp = f"{time.time():.0f}_{abs(hash(body_xml)) % 100000:05d}"
            (outdir / f"{stamp}_request.xml").write_text(envelope, encoding="utf-8")
            (outdir / f"{stamp}_response.xml").write_bytes(response.content)
        if response.status_code >= 400:
            # The body still contains a SOAP Fault — let the parser surface it
            # if possible, otherwise raise the raw HTTP error.
            try:
                _parse_records(response.content, "noop")
            except MetadataSoapError:
                raise
            response.raise_for_status()
        return response.content

    def read_metadata(self, type_name: str, full_names: list[str]) -> list[dict[str, Any]]:
        if not full_names:
            return []
        content = self._post(_read_metadata_body(type_name, full_names), '""')
        return _parse_records(content, "readMetadata")

    def list_metadata(
        self, type_name: str, folder: str | None = None
    ) -> list[dict[str, Any]]:
        content = self._post(
            _list_metadata_body(type_name, folder, self._creds.api_version),
            '""',
        )
        return _parse_records(content, "listMetadata")
