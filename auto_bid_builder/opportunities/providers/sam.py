from __future__ import annotations

from html.parser import HTMLParser
import itertools
import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from ..models import Opportunity


SAM_SEARCH_URL = "https://api.sam.gov/opportunities/v2/search"

# NAICS codes that are strong JTI-adjacent discovery signals. They are used as
# search seeds, not as an automatic bid/no-bid decision.
JTI_NAICS_CODES = (
    "337212",  # Custom Architectural Woodwork and Millwork Manufacturing
    "337215",  # Showcase, Partition, Shelving, and Locker Manufacturing
    "337110",  # Wood Kitchen Cabinet and Countertop Manufacturing
    "238350",  # Finish Carpentry Contractors
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts)


def _with_api_key(url: str, api_key: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["api_key"] = api_key
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _get_json(url: str, *, timeout: float = 30.0) -> dict:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "AutoBidBuilder/0.4"})
    with urlopen(req, timeout=timeout) as response:  # nosec B310 - URL is controlled by provider module
        return json.loads(response.read().decode("utf-8"))


def _get_description(url: str, api_key: str, *, timeout: float = 30.0) -> str:
    req = Request(
        _with_api_key(url, api_key),
        headers={"Accept": "text/html,application/json,text/plain", "User-Agent": "AutoBidBuilder/0.4"},
    )
    with urlopen(req, timeout=timeout) as response:  # nosec B310 - URL originates from SAM.gov response
        body = response.read().decode("utf-8", errors="replace")
    parser = _TextExtractor()
    parser.feed(body)
    text = parser.text() or body
    return text[:50000]


def _place(record: dict) -> tuple[str | None, str | None, str | None]:
    place = record.get("placeOfPerformance") or {}
    city_obj = place.get("city") or {}
    state_obj = place.get("state") or {}
    city = city_obj.get("name") if isinstance(city_obj, dict) else city_obj
    state = state_obj.get("code") if isinstance(state_obj, dict) else state_obj
    postal = place.get("zip") or place.get("zipcode")
    return city, state, postal


def _normalize(record: dict, *, api_key: str, hydrate_description: bool) -> Opportunity:
    city, state, postal = _place(record)
    description_url = record.get("description")
    description = ""
    if hydrate_description and description_url:
        try:
            description = _get_description(description_url, api_key)
        except Exception as exc:  # keep the opportunity even if one description is unavailable
            description = f"[description fetch failed: {type(exc).__name__}]"

    organization = record.get("fullParentPathName") or record.get("department") or record.get("subTier")
    links = record.get("resourceLinks") or []
    if not isinstance(links, list):
        links = []

    # additionalInfoLink is preferred, but SAM also returns uiLink for many public
    # opportunities. Keeping it gives the desktop app something useful to open.
    user_url = record.get("additionalInfoLink") or record.get("uiLink")
    if user_url and not str(user_url).lower().startswith(("http://", "https://")):
        user_url = None

    return Opportunity(
        source="sam.gov",
        external_id=str(record.get("noticeId") or record.get("solicitationNumber") or ""),
        title=str(record.get("title") or "").strip(),
        description=description,
        organization=str(organization).strip() if organization else None,
        posted_date=record.get("postedDate"),
        bid_due_date=record.get("responseDeadLine") or record.get("reponseDeadLine"),
        city=city,
        state=state,
        postal_code=postal,
        naics_code=record.get("naicsCode"),
        classification_code=record.get("classificationCode"),
        url=str(user_url) if user_url else None,
        attachments=tuple(str(x) for x in links),
        metadata={
            "solicitation_number": record.get("solicitationNumber"),
            "notice_type": record.get("type"),
            "set_aside": record.get("typeOfSetAsideDescription") or record.get("setAside"),
            "active": record.get("active"),
            "description_url": description_url,
            "sam_ui_link": record.get("uiLink"),
        },
    )


def _search_once(
    *,
    api_key: str,
    posted_from: str,
    posted_to: str,
    title: str | None,
    state: str | None,
    naics_code: str | None,
    limit: int,
    offset: int = 0,
) -> dict:
    params: dict[str, str | int] = {
        "api_key": api_key,
        "postedFrom": posted_from,
        "postedTo": posted_to,
        "limit": min(max(limit, 1), 1000),
        "offset": max(offset, 0),
    }
    if title:
        params["title"] = title
    if state:
        params["state"] = state
    if naics_code:
        params["ncode"] = naics_code
    return _get_json(f"{SAM_SEARCH_URL}?{urlencode(params)}")


def _search_query_pages(
    *,
    api_key: str,
    posted_from: str,
    posted_to: str,
    title: str | None,
    state: str | None,
    naics_code: str | None,
    page_size: int,
    max_records: int,
) -> list[dict]:
    """Read a bounded number of SAM pages for one search specification.

    SAM documents ``offset`` as a page index, not a record offset. Incrementing it
    by one is therefore important when a query has more results than one page.
    """
    rows: list[dict] = []
    offset = 0
    page_size = min(max(page_size, 1), 1000)
    max_records = max(page_size, max_records)

    while len(rows) < max_records:
        payload = _search_once(
            api_key=api_key,
            posted_from=posted_from,
            posted_to=posted_to,
            title=title,
            state=state,
            naics_code=naics_code,
            limit=min(page_size, max_records - len(rows)),
            offset=offset,
        )
        page = list(payload.get("opportunitiesData") or [])
        rows.extend(page)
        total = int(payload.get("totalRecords") or len(rows))
        if not page or len(rows) >= total or len(page) < page_size:
            break
        offset += 1
    return rows[:max_records]


def search_sam_opportunities(
    *,
    api_key: str,
    posted_from: str,
    posted_to: str,
    titles: tuple[str, ...] = (),
    states: tuple[str, ...] = (),
    naics_codes: tuple[str, ...] = (),
    limit_per_query: int = 100,
    max_records_per_query: int = 500,
    hydrate_descriptions: bool = False,
) -> list[Opportunity]:
    """Search SAM.gov and normalize results.

    SAM's public Opportunities API requires a posted-date range. Multiple title,
    state, and NAICS searches are queried independently and then de-duplicated by
    notice id. This is intentionally discovery-oriented: a generic federal project
    title can still be surfaced because its NAICS or hydrated description indicates
    JTI-adjacent work.
    """

    if not api_key:
        raise ValueError("SAM.gov API key is required")

    states_or_none: tuple[str | None, ...] = tuple(x.upper() for x in states) or (None,)
    query_specs: list[tuple[str | None, str | None, str | None]] = []

    if titles:
        query_specs.extend((title, state, None) for title, state in itertools.product(titles, states_or_none))
    if naics_codes:
        query_specs.extend((None, state, code) for code, state in itertools.product(naics_codes, states_or_none))
    if not query_specs:
        query_specs.extend((None, state, None) for state in states_or_none)

    records: dict[str, dict] = {}
    for title, state, naics_code in query_specs:
        for record in _search_query_pages(
            api_key=api_key,
            posted_from=posted_from,
            posted_to=posted_to,
            title=title,
            state=state,
            naics_code=naics_code,
            page_size=limit_per_query,
            max_records=max_records_per_query,
        ):
            key = str(record.get("noticeId") or record.get("solicitationNumber") or json.dumps(record, sort_keys=True))
            records[key] = record

    return [
        _normalize(record, api_key=api_key, hydrate_description=hydrate_descriptions)
        for record in records.values()
    ]
