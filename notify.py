# -*- coding: utf-8 -*-
"""飞书通知（应用机器人直接私信本人，无需建群）：成稿成功推卡片(速览+链接)，失败/异常推告警。
仅 stdlib。用环境变量：FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_RECEIVE_ID（你的飞书邮箱或 open_id）
/ FEISHU_RECEIVE_ID_TYPE（email|open_id|user_id|mobile，默认 email）。
独立运行用于 workflow 失败兜底：python notify.py "失败原因"。"""
import os
import sys
import json
import urllib.request

BASE = "https://open.feishu.cn/open-apis"


def _token():
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    if not (app_id and app_secret):
        return ""
    req = urllib.request.Request(
        BASE + "/auth/v3/tenant_access_token/internal",
        data=json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        return d.get("tenant_access_token", "") if d.get("code") == 0 else ""
    except Exception:
        return ""


def _send_card(card):
    token = _token()
    receive_id = os.environ.get("FEISHU_RECEIVE_ID", "")
    rid_type = os.environ.get("FEISHU_RECEIVE_ID_TYPE", "email")
    if not token:
        print("飞书 app 未配置 / 取 token 失败，跳过。")
        return False, "no-token"
    if not receive_id:
        print("未配置 FEISHU_RECEIVE_ID，跳过飞书通知。")
        return False, "no-receiver"
    url = BASE + "/im/v1/messages?receive_id_type=" + rid_type
    body = {"receive_id": receive_id, "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False)}
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        return (d.get("code") == 0), str(d)[:200]
    except Exception as e:
        return False, repr(e)


def _card(title, template, md, button_url=""):
    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": md}}]
    if button_url:
        elements.append({"tag": "action", "actions": [{
            "tag": "button", "text": {"tag": "plain_text", "content": "查看完整简报"},
            "url": button_url, "type": "primary"}]})
    return {"config": {"wide_screen_mode": True},
            "header": {"template": template, "title": {"tag": "plain_text", "content": title}},
            "elements": elements}


def notify_success(brief, site_url="", webhook="", secret=""):
    date = brief.get("date", "")
    lede = brief.get("lede") or []
    md = "**北美 · 欧洲市场**\n\n" + "\n".join("• " + str(x) for x in lede[:5])
    if not site_url:
        md += "\n\n_（未配置站点链接）_"
    return _send_card(_card("通机行业每日简报 · " + date, "red", md, site_url))


def notify_failure(text, webhook="", secret=""):
    return _send_card(_card("⚠️ 每日简报生成失败", "red", str(text)[:1000]))


if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "每日 workflow 运行失败。"
    print("飞书告警:", notify_failure(msg))
