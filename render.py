# -*- coding: utf-8 -*-
"""结构化成稿(dict)→ 隆鑫 CI 的成稿 HTML（确定性渲染，不调用任何模型）。
页眉日期由调用方传入（强制 = 当天），logo 内嵌 base64，响应式适配手机。"""
import os
import html as _html
import base64

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(HERE, "assets", "powered-by-loncin.png")

RED = "#E9470B"
GRAY = "#595757"

# 成稿栏目固定顺序：key -> (标题, 副标题)
SECTION_ORDER = [
    ("company", "大公司动向", ""),
    ("product", "新产品", ""),
    ("weather", "灾害天气预警", "发电机 / 水泵需求信号"),
    ("review", "用户评论风向", ""),
    ("policy", "关税 · 排放 · 召回", ""),
]


def _esc(s):
    return _html.escape(s or "", quote=True)


def _logo_uri():
    try:
        with open(LOGO, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    except Exception:
        return ""


def _style():
    return """
  :root{ --red:#E9470B; --red-tint:#fbeae3; --gray:#595757; --muted:#8a8a87; --ink:#2b2b2b; --line:#e6e3da; --surface:#f3f1ea; }
  *{ box-sizing:border-box; }
  body{ margin:0; background:#eceae3; font-family:"Microsoft YaHei","PingFang SC",Calibri,Arial,sans-serif; color:var(--ink); line-height:1.7; }
  .page{ max-width:820px; margin:24px auto; background:#fff; border:0.5px solid var(--line); border-radius:12px; padding:32px 40px; }
  .masthead{ display:flex; justify-content:space-between; align-items:flex-end; border-bottom:3px solid var(--red); padding-bottom:12px; gap:12px; }
  .masthead h1{ font-size:24px; font-weight:500; color:#1a1a1a; margin:0; letter-spacing:1px; }
  .masthead .sub{ font-size:13px; color:var(--muted); margin-top:5px; }
  .org{ text-align:right; }
  .org img{ height:30px; width:auto; display:inline-block; vertical-align:middle; }
  .org .name{ font-size:13px; color:var(--gray); margin-top:5px; }
  .metrics{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:18px 0 6px; }
  .metric{ background:var(--surface); border-radius:8px; padding:10px 12px; }
  .metric .l{ font-size:12px; color:var(--muted); } .metric .v{ font-size:22px; font-weight:500; color:var(--gray); }
  .metric.hot{ background:var(--red-tint); } .metric.hot .l{ color:#b23a1a; } .metric.hot .v{ color:var(--red); }
  .lede{ background:var(--red-tint); border-left:4px solid var(--red); padding:12px 16px; margin:16px 0 20px; }
  .lede h2{ font-size:13px; font-weight:500; color:#b23a1a; margin:0 0 6px; }
  .lede ul{ margin:0; padding-left:18px; font-size:14px; color:#4a4a48; }
  h3.sec{ font-size:16px; font-weight:500; color:var(--gray); margin:22px 0 10px; border-left:4px solid var(--red); padding-left:10px; }
  h3.sec span{ font-size:12px; color:var(--muted); font-weight:400; }
  .item{ font-size:14px; margin-bottom:13px; }
  .item a.t{ color:#1a1a1a; text-decoration:none; border-bottom:1px solid #d8d5cc; }
  .item a.t:hover{ color:var(--red); border-color:var(--red); }
  .item .g{ font-size:13px; color:#555; margin-top:4px; line-height:1.55; }
  .item .d{ color:var(--muted); font-size:12px; margin-top:3px; }
  .nilbox{ font-size:14px; color:#4a4a48; background:var(--surface); border-radius:8px; padding:12px 16px; }
  footer{ border-top:1px solid var(--line); margin-top:24px; padding-top:12px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; }
  footer .src{ font-size:11px; color:#a8a59c; } footer .org2{ font-size:12px; color:var(--gray); }
  @media (max-width:600px){
    body{ background:#fff; }
    .page{ margin:0; border:0; border-radius:0; padding:16px 14px; max-width:100%; }
    .masthead{ flex-wrap:wrap; } .masthead h1{ font-size:20px; } .org img{ height:26px; }
    .metrics{ grid-template-columns:repeat(2,1fr); } .metric .v{ font-size:20px; }
    h3.sec{ font-size:15px; } .item a.t{ font-size:15px; line-height:1.5; }
    footer{ flex-direction:column; align-items:flex-start; }
  }
"""


def _item_html(it):
    title = _esc(it.get("title", ""))
    url = it.get("url", "")
    gist = _esc(it.get("gist", ""))
    src = _esc(it.get("source", ""))
    dt = _esc(it.get("date", ""))
    if url:
        head = '<a class="t" href="%s">%s</a>' % (_esc(url), title)
    else:
        head = '<span class="t" style="border-bottom:1px solid #d8d5cc">%s</span>' % title
    meta = " · ".join([x for x in [src, dt] if x])
    parts = ['<div class="item">', head]
    if gist:
        parts.append('<div class="g">%s</div>' % gist)
    if meta:
        parts.append('<div class="d">%s</div>' % meta)
    parts.append("</div>")
    return "".join(parts)


def render(brief):
    """brief: {date, lede:[...], metrics:[{label,value,hot?}], sections:{key:[item,...]}, note?}"""
    date = _esc(brief.get("date", ""))
    logo = _logo_uri()
    out = []
    out.append("<!DOCTYPE html>")
    out.append('<html lang="zh-CN"><head><meta charset="utf-8">')
    out.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    out.append("<title>通机行业每日简报 · %s</title>" % date)
    out.append("<style>%s</style></head><body>" % _style())
    out.append('<div class="page">')

    # masthead
    org = '<div class="org">'
    if logo:
        org += '<img src="%s" alt="Powered by Loncin">' % logo
    org += '<div class="name">隆鑫通用 · 产品策划部</div></div>'
    out.append('<div class="masthead"><div><h1>通机行业每日简报</h1>'
               '<div class="sub">北美 · 欧洲市场　|　%s</div></div>%s</div>' % (date, org))

    # metrics
    metrics = brief.get("metrics") or []
    if metrics:
        out.append('<div class="metrics">')
        for m in metrics:
            cls = "metric hot" if m.get("hot") else "metric"
            out.append('<div class="%s"><div class="l">%s</div><div class="v">%s</div></div>'
                       % (cls, _esc(str(m.get("label", ""))), _esc(str(m.get("value", "")))))
        out.append("</div>")

    # lede
    lede = brief.get("lede") or []
    if lede:
        out.append('<div class="lede"><h2>今日速览</h2><ul>')
        for b in lede:
            out.append("<li>%s</li>" % _esc(b))
        out.append("</ul></div>")

    sections = brief.get("sections") or {}
    for key, title, sub in SECTION_ORDER:
        items = sections.get(key) or []
        sub_html = ' <span>（%s）</span>' % _esc(sub) if sub else ""
        out.append('<h3 class="sec">%s%s</h3>' % (_esc(title), sub_html))
        if key == "policy" and not items:
            out.append('<div class="nilbox">今日无新增美国联邦关税、非道路 / 小型发动机排放、CPSC 召回公告。持续监测：Federal Register、CPSC、EU Safety Gate。</div>')
        elif not items:
            out.append('<div class="nilbox">今日无相关条目。</div>')
        else:
            for it in items:
                out.append(_item_html(it))

    src_line = _esc(brief.get("source_line",
                    "来源：Federal Register、CPSC、NWS/NHC、Google News、YouTube、Reddit 等公开来源"))
    out.append('<footer><div class="src">%s（%s 采集）</div>'
               '<div class="org2">隆鑫通用 · 产品策划部</div></footer>' % (src_line, date))
    out.append("</div></body></html>")
    return "\n".join(out)
