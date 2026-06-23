# -*- coding: utf-8 -*-
"""飞书通知（应用机器人直发本人，无需建群）：成稿成功推卡片(图 + 速览 + 链接)，失败/异常推告警。
图 = 无头 Chrome 截图本地成稿 HTML → 上传飞书 → 嵌入卡片（拿不到 Chrome 则自动降级为无图卡片）。
仅 stdlib。环境变量：FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_RECEIVE_ID / FEISHU_RECEIVE_ID_TYPE(默认 email，可 mobile)。
所需 app 权限：im:message（发消息）+ contact:user.id:readonly（手机号转 ID）+ im:resource（传图）。
独立运行用于 workflow 失败兜底：python notify.py "失败原因"。"""
import os
import sys
import json
import uuid
import shutil
import subprocess
import tempfile
import urllib.request

BASE = "https://open.feishu.cn/open-apis"


def _token():
    aid = os.environ.get("FEISHU_APP_ID", "")
    sec = os.environ.get("FEISHU_APP_SECRET", "")
    if not (aid and sec):
        return ""
    try:
        req = urllib.request.Request(
            BASE + "/auth/v3/tenant_access_token/internal",
            data=json.dumps({"app_id": aid, "app_secret": sec}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        return d.get("tenant_access_token", "") if d.get("code") == 0 else ""
    except Exception:
        return ""


def _resolve_mobile(mobile, token):
    try:
        req = urllib.request.Request(
            BASE + "/contact/v3/users/batch_get_id?user_id_type=open_id",
            data=json.dumps({"mobiles": [mobile]}).encode("utf-8"), method="POST",
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        ul = (d.get("data") or {}).get("user_list") or []
        return ul[0].get("user_id") if ul and ul[0].get("user_id") else ""
    except Exception:
        return ""


def _chrome():
    for c in [os.environ.get("CHROME_BIN", ""), "google-chrome", "google-chrome-stable",
              "chromium", "chromium-browser"]:
        if c and shutil.which(c):
            return shutil.which(c)
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    return mac if os.path.exists(mac) else ""


def _screenshot(html_path):
    chrome = _chrome()
    if not (chrome and html_path and os.path.exists(html_path)):
        return ""
    out = os.path.join(tempfile.gettempdir(), "brief_shot.png")
    try:
        if os.path.exists(out):
            os.remove(out)
        subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
             "--force-device-scale-factor=2", "--window-size=470,1480",
             "--screenshot=" + out, "file://" + os.path.abspath(html_path)],
            timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return out if os.path.exists(out) else ""
    except Exception:
        return ""


def _upload_image(path, token):
    try:
        img = open(path, "rb").read()
    except Exception:
        return ""
    bd = "----feishu" + uuid.uuid4().hex
    parts = [
        ("--" + bd).encode(), b'Content-Disposition: form-data; name="image_type"', b'', b'message',
        ("--" + bd).encode(), b'Content-Disposition: form-data; name="image"; filename="brief.png"',
        b'Content-Type: image/png', b'', img, ("--" + bd + "--").encode(), b'']
    body = b"\r\n".join(parts)
    try:
        req = urllib.request.Request(
            BASE + "/im/v1/images", data=body, method="POST",
            headers={"Authorization": "Bearer " + token,
                     "Content-Type": "multipart/form-data; boundary=" + bd})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
        return (d.get("data") or {}).get("image_key", "") if d.get("code") == 0 else ""
    except Exception:
        return ""


def _send(card, token):
    rid = os.environ.get("FEISHU_RECEIVE_ID", "")
    rt = os.environ.get("FEISHU_RECEIVE_ID_TYPE", "email")
    if not (token and rid):
        print("飞书未配置完整，跳过通知。")
        return False, "skip"
    if rt == "mobile":
        oid = _resolve_mobile(rid, token)
        if not oid:
            print("手机号转 open_id 失败（app 需 contact:user.id:readonly）。")
            return False, "resolve-fail"
        rid, rt = oid, "open_id"
    try:
        req = urllib.request.Request(
            BASE + "/im/v1/messages?receive_id_type=" + rt,
            data=json.dumps({"receive_id": rid, "msg_type": "interactive",
                             "content": json.dumps(card, ensure_ascii=False)}).encode("utf-8"),
            method="POST",
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        return (d.get("code") == 0), str(d)[:200]
    except Exception as e:
        return False, repr(e)


def _card(title, template, elements):
    return {"config": {"wide_screen_mode": True},
            "header": {"template": template, "title": {"tag": "plain_text", "content": title}},
            "elements": elements}


def notify_success(brief, site_url="", html_path=""):
    token = _token()
    if not token:
        print("飞书 app 未配置，跳过。")
        return False, "no-token"
    date = brief.get("date", "")
    lede = brief.get("lede") or []
    md = "**北美 · 欧洲市场**\n\n" + "\n".join("• " + str(x) for x in lede[:4])
    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": md}}]
    shot = _screenshot(html_path)
    if shot:
        ik = _upload_image(shot, token)
        if ik:
            elements.append({"tag": "img", "img_key": ik,
                             "alt": {"tag": "plain_text", "content": "每日简报"},
                             "mode": "fit_horizontal"})
    if site_url:
        elements.append({"tag": "action", "actions": [{
            "tag": "button", "text": {"tag": "plain_text", "content": "查看完整简报"},
            "url": site_url, "type": "primary"}]})
    return _send(_card("通机行业每日简报 · " + date, "red", elements), token)


def notify_failure(text, *args, **kwargs):
    token = _token()
    if not token:
        print("飞书 app 未配置，跳过告警。")
        return False, "no-token"
    return _send(_card("⚠️ 每日简报生成失败", "red",
                       [{"tag": "div", "text": {"tag": "lark_md", "content": str(text)[:1000]}}]), token)


if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "每日 workflow 运行失败。"
    print("飞书告警:", notify_failure(msg))
