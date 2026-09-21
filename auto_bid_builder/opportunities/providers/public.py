from __future__ import annotations

from html.parser import HTMLParser
import hashlib
import re
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from ..models import Opportunity


USER_AGENT = "AutoBidBuilder/0.2 (+https://github.com/CaMaLabs/Auto_Bid_Builder)"
CCA_URL = "https://ccauthority.org/bid-opportunites/"
DGS_RESD_URL = "https://www.dgs.ca.gov/RESD/Resources/Page-Content/Real-Estate-Services-Division-Resources-List-Folder/Current-Real-Estate-Services-Division-Solicitations"


def _get_text(url: str, *, timeout: float = 25.0) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xml,text/xml,*/*"})
    with urlopen(req, timeout=timeout) as response:  # nosec B310 - configured/public provider URL
        return response.read().decode("utf-8", errors="replace")


def _clean(text: str) -> str:
    return " ".join(text.split())


def _stable_id(source: str, *parts: str) -> str:
    raw = "|".join((source, *parts)).encode("utf-8", errors="replace")
    return hashlib.sha1(raw).hexdigest()[:20]


class _TableParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.rows: list[list[tuple[str, str | None]]] = []
        self._row: list[tuple[str, str | None]] | None = None
        self._cell_parts: list[str] | None = None
        self._cell_link: str | None = None

    def handle_starttag(self, tag: str, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell_parts = []
            self._cell_link = None
        elif tag == "a" and self._cell_parts is not None:
            href = attrs.get("href")
            if href:
                self._cell_link = urljoin(self.base_url, href)

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._row is not None and self._cell_parts is not None:
            self._row.append((_clean("".join(self._cell_parts)), self._cell_link))
            self._cell_parts = None
            self._cell_link = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


class _LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            self._href = urljoin(self.base_url, href) if href else None
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            text = _clean("".join(self._parts))
            if text:
                self.links.append((text, self._href))
            self._href = None
            self._parts = []


def parse_cca_html(html: str, *, source_url: str = CCA_URL) -> list[Opportunity]:
    parser = _TableParser(source_url)
    parser.feed(html)
    rows = parser.rows
    if not rows:
        return []

    header_index = None
    for i, row in enumerate(rows):
        header = " | ".join(cell[0].lower() for cell in row)
        if "project name" in header and ("due" in header or "status" in header):
            header_index = i
            break
    if header_index is None:
        return []

    header = [x[0].lower() for x in rows[header_index]]
    out: list[Opportunity] = []
    for row in rows[header_index + 1 :]:
        if len(row) < 2:
            continue
        values = [x[0] for x in row]
        links = [x[1] for x in row]
        mapping = {header[i]: values[i] for i in range(min(len(header), len(values)))}
        title = mapping.get("project name") or (values[1] if len(values) > 1 else values[0])
        if not title or title.lower() == "project name":
            continue
        location = mapping.get("location") or ""
        due = mapping.get("rfq due date") or mapping.get("bid due date") or mapping.get("due date")
        project_no = mapping.get("project #") or values[0]
        status = mapping.get("status")
        url = next((x for x in links if x), source_url)
        out.append(
            Opportunity(
                source="California Construction Authority",
                external_id=_stable_id("cca", project_no, title, url),
                title=title,
                description=f"Project #{project_no}. Status: {status or 'not supplied'}. Location: {location or 'not supplied'}.",
                organization="California Construction Authority",
                bid_due_date=due or None,
                state="CA",
                url=url,
                metadata={"project_number": project_no, "status": status, "location_text": location, "source_url": source_url},
            )
        )
    return out


def fetch_cca_opportunities(url: str = CCA_URL) -> list[Opportunity]:
    return parse_cca_html(_get_text(url), source_url=url)


def parse_dgs_resd_html(html: str, *, source_url: str = DGS_RESD_URL) -> list[Opportunity]:
    parser = _LinkParser(source_url)
    parser.feed(html)
    out: list[Opportunity] = []
    seen: set[str] = set()
    # DGS construction links are normally titled like "11927B - DEMOLITION ...".
    title_re = re.compile(r"^\s*\d{4,}[A-Z0-9-]*\s*-\s*.+", re.I)
    for title, url in parser.links:
        if not title_re.match(title):
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        project_no = title.split("-", 1)[0].strip()
        out.append(
            Opportunity(
                source="California DGS RESD",
                external_id=_stable_id("dgs-resd", project_no, title, url),
                title=title,
                organization="California Department of General Services - RESD",
                state="CA",
                url=url,
                metadata={"project_number": project_no, "source_url": source_url},
            )
        )
    return out


def fetch_dgs_resd_opportunities(url: str = DGS_RESD_URL) -> list[Opportunity]:
    return parse_dgs_resd_html(_get_text(url), source_url=url)


def _first_text(node: ET.Element, names: tuple[str, ...]) -> str:
    for child in node.iter():
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local in names and child.text and child.text.strip():
            return _clean(child.text)
    return ""


def parse_rss_atom(xml_text: str, *, source_name: str, source_url: str) -> list[Opportunity]:
    root = ET.fromstring(xml_text)
    candidates = [x for x in root.iter() if x.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}]
    out: list[Opportunity] = []
    for item in candidates:
        title = _first_text(item, ("title",))
        if not title:
            continue
        description = _first_text(item, ("description", "summary", "content"))
        published = _first_text(item, ("pubdate", "published", "updated")) or None
        guid = _first_text(item, ("guid", "id"))
        link = ""
        for child in item.iter():
            if child.tag.rsplit("}", 1)[-1].lower() == "link":
                link = child.attrib.get("href") or (child.text or "")
                if link.strip():
                    break
        link = urljoin(source_url, link.strip()) if link.strip() else source_url
        out.append(
            Opportunity(
                source=source_name,
                external_id=guid or _stable_id(source_name, title, link),
                title=title,
                description=description,
                posted_date=published,
                url=link,
                metadata={"source_url": source_url},
            )
        )
    return out


def fetch_rss_atom(url: str, *, source_name: str = "Custom public feed") -> list[Opportunity]:
    return parse_rss_atom(_get_text(url), source_name=source_name, source_url=url)
