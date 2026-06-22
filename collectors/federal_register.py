# -*- coding: utf-8 -*-
"""关税 + 排放：Federal Register API（documents 搜索 + public inspection 预公示）。无需 key。"""
import urllib.parse
from datetime import date, timedelta
from .base import Item, fetch_json, C_TARIFF, C_EMISSION

FR = "https://www.federalregister.gov/api/v1/documents.json"
PI = "https://www.federalregister.gov/api/v1/public-inspection-documents/current.json"
FIELDS = ["title", "abstract", "type", "publication_date", "html_url", "agencies"]


def _build(agencies, types, since, per_page=80):
    params = [("per_page", str(per_page)), ("order", "newest"),
              ("conditions[publication_date][gte]", since)]
    for f in FIELDS:
        params.append(("fields[]", f))
    for a in agencies:
        params.append(("conditions[agencies][]", a))
    for t in types:
        params.append(("conditions[type][]", t))
    return FR + "?" + urllib.parse.urlencode(params)


def _agency_names(doc):
    names = []
    for a in doc.get("agencies", []) or []:
        n = a.get("name") or a.get("raw_name") or ""
        if n:
            names.append(n)
    return ", ".join(names)


def _match(doc, kws):
    if not kws:
        return True
    hay = ((doc.get("title") or "") + " " + (doc.get("abstract") or "")).lower()
    return any(k in hay for k in kws)


def _run(category, agencies, types, kws, since):
    items = []
    try:
        data = fetch_json(_build(agencies, types, since))
    except Exception:
        return items
    for d in data.get("results", []) or []:
        if not _match(d, kws):
            continue
        items.append(Item(category, d.get("title", ""),
                          "Federal Register / " + _agency_names(d),
                          d.get("html_url", ""),
                          (d.get("publication_date") or "")[:10],
                          (d.get("abstract") or "")[:240]))
    return items


def _public_inspection(category_map, since):
    items = []
    try:
        data = fetch_json(PI)
    except Exception:
        return items
    for d in data.get("results", []) or []:
        names = " ".join(d.get("agency_names", []) or []).lower()
        title = d.get("title") or ""
        hay = (title + " " + names).lower()
        for cat in category_map:
            ag_kws, kws = category_map[cat]
            if any(a in names for a in ag_kws) and (not kws or any(k in hay for k in kws)):
                items.append(Item(cat, "[预公示] " + title,
                                  "Federal Register 预公示 / " + ", ".join(d.get("agency_names", []) or []),
                                  d.get("html_url", ""),
                                  (d.get("publication_date") or "")[:10], ""))
                break
    return items


def collect(cfg):
    fr = cfg.get("federal_register", {})
    look = int(cfg.get("lookback_days", 3))
    since = (date.today() - timedelta(days=look)).isoformat()
    tariff_kws = [k.lower() for k in fr.get("tariff_keywords", [])]
    emission_kws = [k.lower() for k in fr.get("emission_keywords", [])]
    items = []
    items += _run(C_TARIFF, fr.get("tariff_agencies", []), fr.get("tariff_types", []), tariff_kws, since)
    items += _run(C_EMISSION, fr.get("emission_agencies", []), fr.get("emission_types", []), emission_kws, since)
    cmap = {
        C_TARIFF: ([a.lower() for a in fr.get("tariff_agency_match", [])], tariff_kws),
        C_EMISSION: ([a.lower() for a in fr.get("emission_agency_match", [])], emission_kws),
    }
    items += _public_inspection(cmap, since)
    return items
