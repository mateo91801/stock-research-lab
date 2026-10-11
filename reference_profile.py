"""Optional supplementary company profile via Wikidata (CC0 public reference data).

Wikidata is community-maintained, not a financial data or verified company filing
source. Matching requires an EXACT exchange ticker in P249 plus similar entity
name; ambiguous entities are never chosen automatically.
"""
from __future__ import annotations
from functools import lru_cache
import re
import requests

API = 'https://www.wikidata.org/w/api.php'
HEADERS = {'User-Agent': 'StockResearchLab/1.4.1 (public company reference; https://github.com/mateo91801/stock-research-lab)'}


def _json(params):
    r = requests.get(API, params={**params, 'format': 'json'}, headers=HEADERS, timeout=8)
    r.raise_for_status()
    return r.json()


def _claim_values(entity, prop):
    vals = []
    for item in (entity.get('claims') or {}).get(prop, []):
        try:
            snak = item['mainsnak']['datavalue']['value']
        except (KeyError, TypeError):
            continue
        vals.append(snak)
    return vals


def _comparable_name(name):
    return [w for w in re.findall(r'[a-z0-9]+',(name or '').lower())
            if w not in {'inc','corp','corporation','company','holding','holdings','plc','ltd','the','incorporated','co'}]


def _name_matches(entity, company):
    company_terms = set(_comparable_name(company))
    entity_terms = set(_comparable_name((entity.get('labels') or {}).get('en',{}).get('value','')))
    return bool(company_terms and entity_terms and (company_terms & entity_terms))


@lru_cache(maxsize=100)
def wikidata_profile(ticker: str, company: str) -> dict:
    """Public metadata only; never a replacement for official fundamentals.

    Returns {} on ambiguity, outages, low-confidence match, or rate limiting.
    """
    if not re.fullmatch(r'[A-Za-z0-9-]{1,12}', ticker or ''):
        return {}
    try:
        search = _json({'action':'wbsearchentities','search':company,'language':'en','limit':'10'})
        ids = [r['id'] for r in search.get('search',[]) if re.fullmatch(r'Q[0-9]+',r.get('id',''))]
        if not ids: return {}
        entities = _json({'action':'wbgetentities','ids':'|'.join(ids),'languages':'en','props':'claims|labels|descriptions'}).get('entities',{})
        candidates = []
        for eid, ent in entities.items():
            listed = [v.strip().upper().replace('.', '-') for v in _claim_values(ent,'P249') if isinstance(v,str)]
            if ticker.upper().replace('.','-') in listed and _name_matches(ent, company):
                candidates.append((eid,ent))
        if len(candidates) != 1: return {}
        qid, entity = candidates[0]
        description = (entity.get('descriptions') or {}).get('en',{}).get('value','').strip()
        # Wikidata English descriptions are brief labels, not audited narratives.
        desc = description[:300]
        hq_ids=[]
        for v in _claim_values(entity, 'P159'):
            if isinstance(v,dict) and isinstance(v.get('id'),str): hq_ids.append(v['id'])
        hq = ''
        if hq_ids:
            places = _json({'action':'wbgetentities','ids':'|'.join(hq_ids[:3]),'languages':'en','props':'labels'}).get('entities',{})
            hq = ', '.join(dict.fromkeys(v.get('labels',{}).get('en',{}).get('value','')
                         for v in places.values() if v.get('labels',{}).get('en',{}).get('value')))
        if not desc and not hq: return {}
        return {'description':desc,'headquarters':hq,'source_url':f'https://www.wikidata.org/wiki/{qid}'}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return {}
