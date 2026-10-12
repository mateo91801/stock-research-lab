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
        # Try the newest 10-Q/10-K and at most two others to limit network use.
        for filed, accession, document, form in sorted(entries, reverse=True)[:3]:
            url = (f'https://www.sec.gov/Archives/edgar/data/{cik}/'
                   f'{accession.replace("-", "")}/{document}')
            try:
                source = _sec_get(url, sec_user_agent, False)
                ceo = extract_ceo_signature(source)
            except (requests.RequestException, ValueError, UnicodeError):
                continue
            if ceo:
                return {**ceo, 'source':f'SEC {form}',
                        'asof':filed, 'source_url':url,
                        'source_note':'Identified from a signed SEC filing; leadership may have changed afterward.'}
        return {}
    except (requests.RequestException, ValueError, KeyError, TypeError, RuntimeError):
        return {}
