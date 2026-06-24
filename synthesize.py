#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""成稿合成器（接地版：模型只引用素材编号 + 逐字证据，代码硬核查 + 回填真链接 → 结构上杜绝编造/404）。

接地三道闸（核心）：
1) 素材编号：把当日原始素材编号 [1..N] 喂给模型；不给 URL，模型也不许写 URL。
2) 证据要求：每个成稿条目必须给 src(所依据的素材编号) + evidence(从该素材逐字复制的英文片段)。
3) 代码硬核查：evidence 必须在被引素材里逐字核到；核到才保留，并由代码回填真 url/来源/日期；
   核不到 → 该条丢弃。gist/速览里 ≥3 位的数字必须能在素材中找到，否则丢弃。
发布的成稿因此只含"能在真实素材里核到"的条目。AI 评审(judge)只做软质量把关(去重/相关/可读)，不再负责防编造。
调用 MiniMax（OpenAI 兼容 /chat/completions）；密钥读环境变量 MINIMAX_API_KEY，仅 stdlib。"""
import os
import sys
import re
import json
import datetime
import urllib.request
import urllib.error

import yaml
import render
import notify

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "briefs", "raw")
OUT_DIR = os.path.join(HERE, "briefs")

SECTION_KEYS = ["company", "product", "weather", "review", "policy"]


# ---------------- 模型调用（唯一外呼处，便于打桩测试）----------------
def call_model(role_cfg, system, user):
    key_env = role_cfg.get("api_key_env", "MINIMAX_API_KEY")
    api_key = os.environ.get(key_env, "")
    if not api_key:
        raise RuntimeError("缺少 MiniMax API key（环境变量 %s）" % key_env)
    url = role_cfg.get("base_url", "https://api.minimaxi.com/v1").rstrip("/") + "/chat/completions"
    body = {
        "model": role_cfg.get("model", "MiniMax-M2"),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": int(role_cfg.get("max_tokens", 16000)),
    }
    if role_cfg.get("temperature") is not None:
        body["temperature"] = float(role_cfg["temperature"])
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=int(role_cfg.get("timeout", 300))) as r:
            resp = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise RuntimeError("MiniMax HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:300]))
    br = resp.get("base_resp") or {}
    if br and br.get("status_code") not in (0, None):
        raise RuntimeError("MiniMax base_resp %s: %s" % (br.get("status_code"), br.get("status_msg")))
    choices = resp.get("choices") or []
    if not choices:
        raise RuntimeError("MiniMax 无 choices：%s" % str(resp)[:300])
    content = (choices[0].get("message") or {}).get("content", "") or ""
    content = re.sub(r"(?s)<think>.*?</think>\s*", "", content).strip()
    return content


def _parse_json(text):
    if not text:
        raise ValueError("空输出")
    t = re.sub(r"\s*```$", "", re.sub(r"^```(?:json)?\s*", "", text.strip()))
    a, b = t.find("{"), t.rfind("}")
    if a == -1 or b == -1:
        raise ValueError("未找到 JSON 对象")
    return json.loads(t[a:b + 1])


def _norm(s):
    """归一化：仅留小写字母+数字，去掉空格/标点/中文，便于逐字子串核查。"""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


# ---------------- 素材编号 + 接地校验 ----------------
def build_index(items):
    """给素材编号；返回 (供模型看的清单文本[不含URL], {id:item})。"""
    id2item, lines = {}, []
    for i, it in enumerate(items, 1):
        id2item[i] = it
        title = (it.get("title") or "").strip()
        summ = (it.get("summary") or "").strip()
        body = title + ((" :: " + summ[:400]) if summ else "")
        lines.append("[%d] (%s) %s 〔%s | %s〕" % (
            i, it.get("category", ""), body, (it.get("date") or "")[:10], it.get("source", "")))
    return "\n".join(lines), id2item


def _src_text(ids, id2item):
    return " ".join(((id2item[x].get("title") or "") + " " + (id2item[x].get("summary") or "")) for x in ids)


def _bad_numbers(text, norm_corpus):
    """text 里 ≥3 位的数字若在 norm_corpus 中找不到，返回这些数字（疑似编造）。"""
    bad = []
    for n in re.findall(r"\d[\d,\.]*\d|\d", text or ""):
        nn = _norm(n)
        if len(nn) >= 3 and nn not in norm_corpus:
            bad.append(n)
    return bad


def verify_and_fill(brief, id2item):
    """硬接地校验：保留能核到 evidence 的条目并回填真 url/来源/日期；丢弃核不到的。返回 (clean_brief, issues)。"""
    issues = []
    secs = brief.get("sections") or {}
    clean = {}
    for key in SECTION_KEYS:
        kept = []
        for it in (secs.get(key) or []):
            src = it.get("src")
            ids = src if isinstance(src, list) else [src]
            ids = [x for x in ids if isinstance(x, int) and x in id2item]
            tt = (it.get("title") or "")[:24]
            if not ids:
                issues.append("[%s] 引用了不存在的素材编号(src=%r)，丢弃：%s" % (key, src, tt))
                continue
            corpus = _norm(_src_text(ids, id2item))
            nev = _norm(it.get("evidence") or "")
            if len(nev) < 12 or nev not in corpus:
                issues.append("[%s] evidence 无法在被引素材中逐字核到，疑似编造，丢弃：%s" % (key, tt))
                continue
            bad = _bad_numbers((it.get("title") or "") + " " + (it.get("gist") or ""), corpus)
            if bad:
                issues.append("[%s] 标题/小结含素材中没有的数字%s，疑似编造，丢弃：%s" % (key, bad, tt))
                continue
            p = id2item[ids[0]]
            kept.append({"title": it.get("title", ""), "gist": it.get("gist", ""),
                         "url": p.get("url", ""), "source": p.get("source", ""),
                         "date": (p.get("date") or "")[:16]})
        clean[key] = kept
    out = dict(brief)
    out["sections"] = clean
    full = _norm(_src_text(list(id2item.keys()), id2item))
    good_lede = []
    for b in (brief.get("lede") or []):
        bad = _bad_numbers(b, full)
        if bad:
            issues.append("速览含素材中没有的数字%s，剔除：%s" % (bad, b[:24]))
            continue
        good_lede.append(b)
    out["lede"] = good_lede
    return out, issues


# ---------------- Prompt（日期由代码注入；模型只给编号+证据）----------------
def gen_prompt(today, cutoff, listing):
    system = (
        "你是隆鑫通用·产品策划部的资深通机行业分析师。**只能依据下方编号素材**撰写面向中国读者的中文每日简报"
        "（北美·欧洲市场口径）。严格输出 JSON，不要任何解释。\n"
        "【最高铁律——违反即作废】\n"
        "1) 只准使用编号素材里出现的事实；**禁止引入素材之外的任何信息**（公司/型号/参数/数字/事件都不许补充或想象）。\n"
        "2) 每个条目必须给 src（所依据的素材编号，整数或整数数组）+ evidence（从该素材里**逐字复制**的一段英文原文，≥12 字符，用来自证不是编的）。\n"
        "3) **绝不要写任何网址/URL/链接**——系统自动回填，写了也会被删。\n"
        "4) title、gist 用中文，但必须是对 evidence 的忠实转述；**不得出现 evidence 里没有的数字或细节**。\n"
        "【其他要求】\n"
        "5) 时效：今天=%s；发布日期早于 %s 的素材不要用。\n"
        "6) 只保留与 发电机/通用汽油发动机/割草机器人/水泵/微耕机/草坪车 相关、且北美或欧洲市场的；剔除拍卖/备件电商/无关时政/非目标市场噪音。\n"
        "7) 归类 5 栏目：company/product/weather/review/policy；同主题聚合(src 给多个编号)、去重、按重要性排序；policy 无则空数组。\n"
        "8) 禁止推测标注括号、禁止 AI 痕迹与内部文档名；全中文。\n"
        "输出 JSON：{\"lede\":[\"3-4 条今日速览(只用素材内事实)\"],"
        "\"sections\":{\"company\":[{\"title\":\"\",\"gist\":\"\",\"src\":[编号],\"evidence\":\"逐字英文原文片段\"}],"
        "\"product\":[],\"weather\":[],\"review\":[],\"policy\":[]}}"
        % (today, cutoff)
    )
    user = "今天=%s。编号素材如下，**只能用这些**：\n%s" % (today, listing)
    return system, user


def judge_prompt(today, brief):
    system = (
        "你是中文简报质检员，只把关**可读性与编辑质量**(事实真伪已由系统核过，无需你判断)。只输出 JSON。\n"
        "检查：A) 每条 gist 非空、通顺、是对标题的合理展开；B) 同主题无重复条目；"
        "C) 与 6 类通机产品 + 北美/欧洲相关、无明显噪音；D) 无 AI 痕迹/内部文档名；全中文；E) 速览 3-4 条且与正文一致。\n"
        "满足输出 {\"verdict\":\"PASS\",\"issues\":[]}；否则 {\"verdict\":\"REJECT\",\"issues\":[\"可执行的修改意见\"]}。"
    )
    return system, "待审成稿(JSON)：\n%s" % json.dumps(brief, ensure_ascii=False)


def revise_user(prev, issues, today, cutoff):
    return (
        "今天=%s；时效线=%s。你上一版有问题，按意见重写并只输出同结构 JSON(仍须给 src+evidence、不写 URL、不引入素材外信息)：\n"
        "意见：\n- %s\n\n上一版：\n%s"
        % (today, cutoff, "\n- ".join(issues), json.dumps(prev, ensure_ascii=False))
    )


# ---------------- 编排 ----------------
def build_metrics(raw):
    from collections import Counter
    items = raw.get("items", [])
    c = Counter(it.get("category", "") for it in items)
    return [
        {"label": "今日监测条目", "value": len(items)},
        {"label": "大公司动向", "value": c.get("大公司动向", 0)},
        {"label": "新品 / 评测", "value": "%d / %d" % (c.get("新产品", 0), c.get("用户评论风向", 0))},
        {"label": "天气预警", "value": c.get("灾害天气预警", 0), "hot": True},
    ]


def write_archive(today, html):
    os.makedirs(OUT_DIR, exist_ok=True)
    day_path = os.path.join(OUT_DIR, today + ".html")
    with open(day_path, "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(OUT_DIR, "latest.html"), "w", encoding="utf-8") as f:
        f.write(html)
    rebuild_index()
    return day_path


def rebuild_index():
    days = sorted([m.group(1) for fn in os.listdir(OUT_DIR)
                   for m in [re.match(r"^(\d{4}-\d{2}-\d{2})\.html$", fn)] if m], reverse=True)
    lines = ['<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             "<title>通机行业每日简报 · 存档</title>",
             '<style>body{font-family:"Microsoft YaHei",Calibri,sans-serif;max-width:720px;margin:24px auto;'
             'padding:0 16px;color:#2b2b2b}h1{font-size:20px;color:#595757;border-bottom:3px solid #E9470B;'
             'padding-bottom:8px}a{color:#1a1a1a;text-decoration:none}li{margin:8px 0;font-size:15px}'
             '.org{color:#595757;font-size:12px;margin-top:20px}</style></head><body>',
             "<h1>通机行业每日简报 · 存档</h1>",
             '<p style="font-size:13px;color:#8a8a87">最新一期见 <a href="latest.html">latest.html</a>。以下按日期累积：</p>',
             "<ul>"]
    for d in days:
        lines.append('<li><a href="%s.html">%s</a></li>' % (d, d))
    lines.append("</ul><div class='org'>隆鑫通用 · 产品策划部</div></body></html>")
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _total(filled):
    return sum(len(v) for v in (filled.get("sections") or {}).values())


def main():
    cfg = yaml.safe_load(open(os.path.join(HERE, "sources.yaml"), encoding="utf-8"))
    sc = cfg.get("synthesis", {})
    site_url = os.environ.get("SITE_URL", sc.get("site_url", ""))
    today = datetime.date.today().isoformat()
    cutoff = (datetime.date.today() - datetime.timedelta(days=int(sc.get("new_within_days", 5)))).isoformat()
    max_retries = int(sc.get("max_retries", 3))

    raw_path = os.path.join(RAW_DIR, today + ".json")
    if not os.path.exists(raw_path):
        print("无当日原始素材：%s，跳过合成。" % raw_path)
        return 0
    raw = json.load(open(raw_path, encoding="utf-8"))
    listing, id2item = build_index(raw.get("items", []))

    common = {"base_url": sc.get("base_url", "https://api.minimaxi.com/v1"),
              "api_key_env": sc.get("api_key_env", "MINIMAX_API_KEY")}

    def role_cfg(name, default_model):
        d = dict(common)
        d.update(sc.get("models", {}).get(name, {}))
        d.setdefault("model", default_model)
        return d

    gen_cfg = role_cfg("generator", "MiniMax-M2.7")
    judge_cfg = role_cfg("judge", "MiniMax-M2.5")

    g_sys, g_user = gen_prompt(today, cutoff, listing)
    parsed, filled, last_issues = None, None, []
    for attempt in range(1, max_retries + 1):
        text = call_model(gen_cfg, g_sys, g_user if attempt == 1 else revise_user(parsed, last_issues, today, cutoff))
        try:
            parsed = _parse_json(text)
        except Exception as e:
            last_issues = ["上版不是合法 JSON（%r），只输出规定结构 JSON。" % e]
            print("第 %d 次：JSON 解析失败，反馈重写。" % attempt)
            continue

        filled, hard_issues = verify_and_fill(parsed, id2item)
        total = _total(filled)
        j_issues = []
        if total > 0:
            j_sys, j_user = judge_prompt(today, filled)
            try:
                verdict = _parse_json(call_model(judge_cfg, j_sys, j_user))
            except Exception:
                verdict = {"verdict": "PASS"}  # 质检挂了不阻断（接地已由代码保证）
            if str(verdict.get("verdict", "")).upper() != "PASS":
                j_issues = verdict.get("issues", []) or []

        print("第 %d 次：接地保留 %d 条，丢弃 %d 条；质量意见 %d 条。" % (attempt, total, len(hard_issues), len(j_issues)))
        if total > 0 and not hard_issues and not j_issues:
            break
        last_issues = (hard_issues + j_issues) or ["请改进质量。"]

    if not filled or _total(filled) == 0:
        marker = os.path.join(RAW_DIR, today + ".review-failed.txt")
        with open(marker, "w", encoding="utf-8") as f:
            f.write("接地校验后无可发布条目（疑似全部编造或无匹配素材）。最后意见：\n- %s\n" % "\n- ".join(last_issues))
        print("⚠️ 接地后无可发布条目，未发布。")
        notify.notify_failure("今日成稿接地校验后无可发布条目（疑似编造已全部拦下），未发布。")
        return 0

    # 发布（filled 已保证逐条接地、链接为代码回填的真链接）
    filled["date"] = today
    filled["metrics"] = build_metrics(raw)
    filled["sections"] = {k: (filled.get("sections") or {}).get(k, []) for k in SECTION_KEYS}
    html = render.render(filled)
    path = write_archive(today, html)
    print("已发布成稿：%s（接地后 %d 条）" % (path, _total(filled)))
    notify.notify_success(filled, site_url, os.path.join(OUT_DIR, "latest.html"))
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        notify.notify_failure("synthesize 运行异常：%r" % e)
        sys.exit(1)
    sys.exit(rc)
