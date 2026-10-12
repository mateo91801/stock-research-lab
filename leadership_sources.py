"""Supplement optional executive metadata with verified-at-filing SEC signatures.

This module is deliberately conservative: if it cannot unambiguously identify a
CEO signing a recent official 10-Q/10-K, it returns no CEO instead of guessing.
A signature is evidence of the person's title ON THE FILING DATE, not a claim
that the person necessarily still holds the role today.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import re

import requests


class _FilingText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag in ('p', 'br', 'div', 'tr', 'td', 'th', 'table', 'section', 'h1', 'h2', 'h3'):
            self.text.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        if tag in ('p', 'div', 'tr', 'td', 'th', 'table', 'section', 'h1', 'h2', 'h3'):
            self.text.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


def extract_ceo_signature(document_html: str) -> dict:
    """Find a named SEC /s/ signature paired with an explicit CEO role.

    Avoid name extraction from biographical tables (which may include past CEOs).
    Only signed roles are eligible. Return empty on ambiguity.
    """
    reader = _FilingText()
    reader.feed(document_html)
    text = unescape(''.join(reader.text)).replace('\xa0', ' ')
    # SEC documents vary in markup. Most signatures are near the end, not all.
    lines = [re.sub(r'\s+', ' ', line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    matches = []
    for i, line in enumerate(lines):
        if not re.search(r'/s/', line, flags=re.I):
            continue
        name = re.split(r'/s/', line, maxsplit=1, flags=re.I)[-1].strip()
        if not name and i + 1 < len(lines):
            name = lines[i + 1].strip()
        name = re.sub(r'^(?:by\s*:\s*)', '', name, flags=re.I).strip(' :,')
        if not re.fullmatch(r"[A-Za-z][A-Za-z.\-’' ]{3,74}", name):
            continue
        # The same person/title might appear in many paragraphs; require the
        # person's *signed* office to be explicitly CEO within nearby lines.
        next_lines = []
        for more in lines[i + 1:i + 10]:
            if '/s/' in more.lower():
                break
            next_lines.append(more)
        context = ' '.join(next_lines[:8])
        if not re.search(r'\b(?:chief executive officer|principal executive officer)\b', context, flags=re.I):
            continue
        # Don't mistake the CFO/CAO signatory for the CEO when a document's
        # adjacent signatures are tightly formatted.
        role = 'Chair and Chief Executive Officer' if re.search(
            r'\bchair(?:man|woman|person)?\b', context[:180], flags=re.I
        ) else 'Chief Executive Officer'
        matches.append((name.title(), role))
    # Ignore duplicate references to the same signatory. Conflicting names
    # are not resolved by guessing which appears last in the document.
    distinct = {name.lower(): (name, title) for name, title in matches}
    return dict(zip(('name', 'title'), next(iter(distinct.values())))) if len(distinct) == 1 else {}




def extract_ceo_certification(document_html: str) -> dict:
    """Parse a signed 10-K/10-Q Exhibit 31 CEO certification.

    The signer must identify themselves in the first-person certification AND
    sign under the same name. A CEO title must appear in the exhibit. We only
    call this on SEC exhibit candidates; biographies and press releases are not
    eligible evidence.
    """
    reader = _FilingText()
    reader.feed(document_html)
    document = unescape(' '.join(reader.text)).replace('\xa0', ' ')
    document = re.sub(r'\s+', ' ', document)
    if not re.search(r'\bchief executive officer\b', document, re.I):
        return {}
    candidates = []
    pattern = r'\bI,\s*([A-Za-z][A-Za-z.\u2019\u0027\- ]{3,85}?)\s*,\s*certify\s+that\b'
    for match in re.finditer(pattern, document, re.I):
        name = re.sub(r'\s+', ' ', match.group(1)).strip()
        if len(name.split()) < 2 or len(name.split()) > 6:
            continue
        if re.search(r'/s/\s*' + re.escape(name) + r'\b', document, re.I):
            candidates.append(name)
    distinct = {name.casefold(): name for name in candidates}
    if len(distinct) != 1:
        return {}
    return {'name': next(iter(distinct.values())), 'title': 'Chief Executive Officer'}


def _certification_documents(index_data: dict) -> list[str]:
    """Choose only plausible 31.1 exhibit filenames from an SEC index.

    This is a candidate filter, not evidence by itself: each candidate still
    requires a matching first-person CEO certification and signature.
    """
    items = (index_data.get('directory') or {}).get('item') or []
    names = []
    for item in items:
        name = str(item.get('name') or '') if isinstance(item, dict) else ''
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,150}\.html?', name, re.I):
            continue
        if re.search(r'(?:ex(?:hibit)?[-_.]?31|31[-_.]?1|certif)', name, re.I):
            names.append(name)
    return names[:3]

def _sec_get(url, user_agent, as_json):
    result = requests.get(url, timeout=15, headers={
        'User-Agent': user_agent,
        'Accept-Encoding': 'gzip, deflate',
        'Accept': 'application/json' if as_json else 'text/html',
    })
    result.raise_for_status()
    if len(result.content) > 12_000_000:
        raise ValueError('SEC document too large for management lookup')
    return result.json() if as_json else result.text


def _request_failure(exc: Exception) -> str:
    """Safe, user-facing network status: never expose URLs or contact secrets."""
    if isinstance(exc, requests.HTTPError):
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
        if status in (403, 429):
            return f'HTTP {status}: access denied or rate-limited'
        if isinstance(status, int):
            return f'HTTP {status}: SEC service request failed'
    if isinstance(exc, requests.Timeout):
        return 'request timed out'
    if isinstance(exc, (requests.RequestException, ConnectionError)):
        return 'network request failed'
    return 'SEC response could not be read'


def sec_ceo_from_recent_filing_diagnostic(ticker: str, sec_user_agent: str) -> tuple[dict, str]:
    """Return (verified CEO, user-friendly diagnostic) without guessing.

    Do not cache failures here: an SEC outage should not persist after recovery.
    The caller can independently cache stock data for a bounded interval.
    """
    from sec_fundamentals import valid_agent, sec_cik

    if not valid_agent(sec_user_agent):
        return {}, ('SEC lookup not started: SEC_USER_AGENT is missing or does not '
                    'contain a valid contact email in Streamlit Secrets.')

    try:
        cik = sec_cik(ticker, sec_user_agent)
    except (requests.RequestException, ValueError, KeyError, TypeError, RuntimeError) as exc:
        return {}, ('SEC ticker directory unavailable (' + _request_failure(exc) +
                    '). Retry later; check the Streamlit server logs if it persists.')
    if not cik:
        return {}, 'SEC lookup stopped: no SEC company identifier found for this ticker.'

    try:
        submissions = _sec_get(
            f'https://data.sec.gov/submissions/CIK{cik:010d}.json',
            sec_user_agent, True,
        )
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        return {}, ('SEC submissions unavailable (' + _request_failure(exc) +
                    '). The Lab cannot confirm an executive from filings right now.')

    recent = (submissions.get('filings') or {}).get('recent') or {}
    entries = []
    for form, accession, document, filed in zip(
        recent.get('form', []), recent.get('accessionNumber', []),
        recent.get('primaryDocument', []), recent.get('filingDate', []),
    ):
        if form not in ('10-Q', '10-K'):
            continue
        if not re.fullmatch(r'\d{10}-\d{2}-\d{6}', str(accession)):
            continue
        if not re.fullmatch(r'[A-Za-z0-9_\-.]+\.html?', str(document), re.I):
            continue
        try:
            age_days = (datetime.now(timezone.utc).date() -
                        datetime.strptime(str(filed), '%Y-%m-%d').date()).days
        except ValueError:
            continue
        if 0 <= age_days <= 540:
            entries.append((str(filed), str(accession), str(document), form))

    if not entries:
        return {}, 'SEC submissions loaded, but no eligible 10-K or 10-Q filed within the last 540 days.'

    failed_downloads = []
    readable_documents = 0
    # Limit requests to the two most recent eligible filings.
    for filed, accession, document, form in sorted(entries, reverse=True)[:2]:
        archive = (f'https://www.sec.gov/Archives/edgar/data/{cik}/'
                   f'{accession.replace("-", "")}/')
        url = archive + document
        try:
            html = _sec_get(url, sec_user_agent, False)
            readable_documents += 1
            ceo = extract_ceo_signature(html)
        except (requests.RequestException, ValueError, UnicodeError) as exc:
            failed_downloads.append(_request_failure(exc))
            ceo = {}
        if ceo:
            return ({**ceo, 'source': f'SEC {form} signed filing',
                     'asof': filed, 'source_url': url,
                     'source_note': 'Signed SEC filing; title verified on filing date, not necessarily today.'},
                    f'CEO verified in SEC {form} signature dated {filed}.')

        try:
            index = _sec_get(archive + 'index.json', sec_user_agent, True)
            exhibits = _certification_documents(index)
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            failed_downloads.append(_request_failure(exc))
            exhibits = []
        for exhibit in exhibits:
            exhibit_url = archive + exhibit
            try:
                html = _sec_get(exhibit_url, sec_user_agent, False)
                readable_documents += 1
                ceo = extract_ceo_certification(html)
            except (requests.RequestException, ValueError, UnicodeError) as exc:
                failed_downloads.append(_request_failure(exc))
                continue
            if ceo:
                return ({**ceo, 'source': f'SEC {form} Exhibit 31 certification',
                         'asof': filed, 'source_url': exhibit_url,
                         'source_note': 'CEO signed certification; later leadership changes are possible.'},
                        f'CEO verified in SEC {form} Exhibit 31 dated {filed}.')

    if failed_downloads:
        detail = '; '.join(sorted(set(failed_downloads)))
        if not readable_documents:
            return {}, ('SEC filings were located, but their archive files could not '
                        f'be downloaded ({detail}). This may be a temporary access restriction.')
        return {}, ('Some SEC documents were read, but other filing files were inaccessible '
                    f'({detail}); no unambiguous signed CEO was verified.')

    return {}, ('Recent SEC filing documents were read, but no unambiguous CEO signature '
                'or CEO-signed Exhibit 31 certification was found. The Lab will not guess.')


def sec_ceo_from_recent_filing(ticker: str, sec_user_agent: str) -> dict:
    """Backward-compatible verified CEO lookup for callers needing only the record."""
    result, _ = sec_ceo_from_recent_filing_diagnostic(ticker, sec_user_agent)
    return result
