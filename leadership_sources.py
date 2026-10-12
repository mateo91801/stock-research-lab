"""Supplement optional executive metadata with verified-at-filing SEC signatures.

This module is deliberately conservative: if it cannot unambiguously identify a
CEO signing a recent official 10-Q/10-K, it returns no CEO instead of guessing.
A signature is evidence of the person's title ON THE FILING DATE, not a claim
that the person necessarily still holds the role today.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
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


@lru_cache(maxsize=50)
def sec_ceo_from_recent_filing(ticker: str, sec_user_agent: str) -> dict:
    """Only return CEO confirmed by a recent 10-Q/10-K signature.

    The SEC's XBRL *companyfacts* endpoint has NO CEO field. This therefore
    reads a limited set of official filing documents, only when Yahoo is blank.
    """
    from sec_fundamentals import valid_agent, sec_cik
    if not valid_agent(sec_user_agent):
        return {}
    try:
        cik = sec_cik(ticker, sec_user_agent)
        if not cik:
            return {}
        submissions = _sec_get(
            f'https://data.sec.gov/submissions/CIK{cik:010d}.json',
            sec_user_agent, True,
        )
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
            if not 0 <= age_days <= 540:
                continue
            entries.append((str(filed), str(accession), str(document), form))
        # Examine at most two recent filings. The main document can be signed
        # only by a CFO; Exhibit 31.1 often separately certifies the CEO.
        for filed, accession, document, form in sorted(entries, reverse=True)[:2]:
            archive = (f'https://www.sec.gov/Archives/edgar/data/{cik}/'
                       f'{accession.replace("-", "")}/')
            url = archive + document
            try:
                ceo = extract_ceo_signature(_sec_get(url, sec_user_agent, False))
            except (requests.RequestException, ValueError, UnicodeError):
                ceo = {}
            if ceo:
                return {**ceo, 'source': f'SEC {form} signed filing',
                        'asof': filed, 'source_url': url,
                        'source_note': 'Signed SEC filing; office is verified on the filing date, not today.'}

            try:
                index = _sec_get(archive + 'index.json', sec_user_agent, True)
                exhibits = _certification_documents(index)
            except (requests.RequestException, ValueError, KeyError, TypeError):
                exhibits = []
            for exhibit in exhibits:
                exhibit_url = archive + exhibit
                try:
                    ceo = extract_ceo_certification(_sec_get(exhibit_url, sec_user_agent, False))
                except (requests.RequestException, ValueError, UnicodeError):
                    continue
                if ceo:
                    return {**ceo, 'source': f'SEC {form} Exhibit 31 certification',
                            'asof': filed, 'source_url': exhibit_url,
                            'source_note': 'CEO certified and signed this filing; later leadership changes are possible.'}
        return {}
    except (requests.RequestException, ValueError, KeyError, TypeError, RuntimeError):
        return {}
