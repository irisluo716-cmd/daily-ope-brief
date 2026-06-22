# -*- coding: utf-8 -*-
"""通用工具：HTTP 抓取（UA / 重试 / 退避）、RSS+Atom 解析、Item 数据结构、分类常量。
兼容 Python 3.7（不使用 walrus / removeprefix / dict 合并等 3.8+ 语法）。"""
import json
import time
import html
import re
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict

# ---- 7 大分类（顺序即成稿顺序）----
C_COMPANY = "大公司动向"
C_PRODUCT = "新产品"
C_WEATHER = "灾害天气预警"
C_REVIEW = "用户评论风向"
C_TARIFF = "关税"
C_EMISSION = "排放"
C_RECALL = "CPSC召回与产品安全"
CATEGORY_ORDER = [C_COMPANY, C_PRODUCT, C_WEATHER, C_REVIEW, C_TARIFF, C_EMISSION, C_RECALL]

DEFAULT_UA = "daily-ope-brief/0.1 (industry news digest; contact: iris.luo716@gmail.com)"


@dataclass
class Item:
    category: str
    title: str
    source: str = ""
    url: str = ""
    date: str = ""
    summary: str = ""

    def key(self):
        # url + title 组合去重：同链接同标题才算重复；天气等共用链接、标题不同的不会被误折叠
        u = (self.url or "").strip().lower()
        t = (self.title or "").strip().lower()
        return (u + "|" + t) if u else t

    def to_dict(self):
        return asdict(self)


def fetch(url, headers=None, retries=3, backoff=2, timeout=30):
    """返回 bytes。对 429 / 5xx 退避重试，其余 HTTP 错误直接抛。"""
    h = {"User-Agent": DEFAULT_UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503):
                time.sleep(backoff * (i + 1))
                continue
            raise
        except Exception as e:
            last = e
            time.sleep(backoff * (i + 1))
    if last:
        raise last
    raise RuntimeError("fetch failed: " + url)


def fetch_json(url, headers=None, retries=3, backoff=2, timeout=30):
    raw = fetch(url, headers=headers, retries=retries, backoff=backoff, timeout=timeout)
    return json.loads(raw.decode("utf-8", "replace"))


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _localname(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


def _txt(parent, name):
    el = parent.find(name)
    if el is not None and el.text:
        return el.text.strip()
    return ""


def parse_feed(data):
    """解析 RSS2.0 与 Atom，返回 [{title, link, date, summary}]。无法解析时返回 []。"""
    out = []
    try:
        root = ET.fromstring(data) if isinstance(data, (bytes, str)) else data
    except ET.ParseError:
        return out
    # 去命名空间，统一用 localname
    for el in root.iter():
        el.tag = _localname(el.tag)
    # RSS 2.0
    for it in root.iter("item"):
        out.append({
            "title": strip_html(_txt(it, "title")),
            "link": _txt(it, "link"),
            "date": _txt(it, "pubDate"),
            "summary": strip_html(_txt(it, "description")),
        })
    # Atom
    for it in root.iter("entry"):
        link = ""
        l = it.find("link")
        if l is not None:
            link = l.get("href") or (l.text or "")
        out.append({
            "title": strip_html(_txt(it, "title")),
            "link": link or _txt(it, "link"),
            "date": _txt(it, "updated") or _txt(it, "published"),
            "summary": strip_html(_txt(it, "summary") or _txt(it, "content")),
        })
    return out
