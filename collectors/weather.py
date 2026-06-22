# -*- coding: utf-8 -*-
"""灾害天气预警（发电机 / 水泵需求信号）：NWS 活跃预警聚合 + NHC 活跃热带气旋。无需 key。
注：Meteoalarm（欧洲）/ PowerOutage 暂未自动接入，见 README 待办。"""
from collections import Counter, defaultdict
from datetime import date
from .base import Item, fetch_json, C_WEATHER, DEFAULT_UA

NWS_ALERTS = ("https://api.weather.gov/alerts/active"
              "?status=actual&severity=Severe,Extreme")
NWS_PAGE = "https://www.weather.gov/"
NHC_JSON = "https://www.nhc.noaa.gov/CurrentStorms.json"
NHC_PAGE = "https://www.nhc.noaa.gov/"


def collect(cfg):
    wc = cfg.get("weather", {})
    evkws = [e.lower() for e in wc.get("event_keywords", [])]
    items = []
    today = date.today().isoformat()

    # 1) NWS 活跃预警 —— 聚合到事件类型，避免逐县刷屏
    try:
        data = fetch_json(NWS_ALERTS, headers={"User-Agent": DEFAULT_UA,
                                               "Accept": "application/geo+json"})
        counts = Counter()
        areas = defaultdict(list)
        for f in data.get("features", []) or []:
            p = f.get("properties", {}) or {}
            ev = p.get("event", "") or ""
            if evkws and not any(k in ev.lower() for k in evkws):
                continue
            counts[ev] += 1
            a = p.get("areaDesc", "") or ""
            if a and len(areas[ev]) < 3:
                areas[ev].append(a.split(";")[0][:40])
        for ev, c in counts.most_common(12):
            items.append(Item(C_WEATHER, "%s — %d 条活跃预警" % (ev, c),
                              "NWS", NWS_PAGE, today,
                              "示例区域: " + " / ".join(areas[ev])))
    except Exception:
        pass

    # 2) NHC 活跃热带气旋
    try:
        cs = fetch_json(NHC_JSON, headers={"User-Agent": DEFAULT_UA})
        for s in cs.get("activeStorms", []) or []:
            name = s.get("name", "") or ""
            cls = s.get("classification", "") or ""
            inten = s.get("intensity", "") or ""
            title = ("%s %s（强度 %s kt）" % (cls, name, inten)).strip()
            items.append(Item(C_WEATHER, title, "NHC 国家飓风中心", NHC_PAGE,
                              (s.get("lastUpdate") or "")[:10],
                              "盆地: %s" % s.get("binNumber", "")))
    except Exception:
        pass

    return items
