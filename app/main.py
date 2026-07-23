"""微信草稿 relay：微信接口的纯代理（零三方依赖，仅用标准库）。

端点：
  GET  /health          健康检查（含当前鉴权模式）
  POST /material        上传图片到素材库 -> {"media_id":..., "url":...}
  POST /draft           创建草稿 -> {"media_id":...}
  POST /draft-delete    删除草稿 -> {"errcode":0, "errmsg":"ok"}

/material  JSON: {"name": "img/body1.png", "data_b64": "..."}
  -> {"media_id": "...", "url": "https://mmbiz.qpic.cn/..."}

/draft  JSON: {"title": "...", "content_html": "<section>...</section>",
               "thumb_media_id": "...", "author": "", "digest": ""}
  -> {"media_id": "..."}

两个写接口都受 X-API-Key 保护（若配置了 RELAY_API_KEY）。
markdown -> HTML 的转换在客户端（skill）完成，relay 不碰 markdown。
"""
import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from app import config, wechat


def _upload_material(payload: dict) -> dict:
    name = payload.get("name") or "img.png"
    data = base64.b64decode(payload.get("data_b64") or "")
    if not data:
        raise ValueError("data_b64 不能为空")
    up = wechat.upload_image(data, name)
    return {"media_id": up["media_id"], "url": up["url"]}


def _create_draft(payload: dict) -> dict:
    title = (payload.get("title") or "").strip()
    html = payload.get("content_html") or ""
    thumb = payload.get("thumb_media_id") or ""
    if not title:
        raise ValueError("title 不能为空")
    if not html:
        raise ValueError("content_html 不能为空")
    if not thumb:
        raise ValueError("thumb_media_id 不能为空")
    media_id = wechat.add_draft(
        title=title,
        content_html=html,
        thumb_media_id=thumb,
        author=payload.get("author") or config.DEFAULT_AUTHOR,
        digest=payload.get("digest") or "",
    )
    return {"media_id": media_id}


def _delete_draft(payload: dict) -> dict:
    media_id = (payload.get("media_id") or "").strip()
    if not media_id:
        raise ValueError("media_id 不能为空")
    return wechat.delete_draft(media_id)


class Handler(BaseHTTPRequestHandler):
    server_version = "wechat-draft-relay/1.0"

    def _send_json(self, code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # 静默默认访问日志
        pass

    def do_GET(self):
        if urlparse(self.path).path in ("/", "/health"):
            self._send_json(200, {
                "ok": True,
                "mode": "cloudcall" if config.WX_CLOUDCALL else "token",
            })
        else:
            self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/material", "/draft", "/draft-delete"):
            self._send_json(404, {"ok": False, "error": "not found"})
            return

        key = self.headers.get("X-API-Key")
        if config.RELAY_API_KEY and key != config.RELAY_API_KEY:
            self._send_json(401, {"ok": False, "error": "invalid api key"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8"))
            if path == "/material":
                result = _upload_material(payload)
            elif path == "/draft":
                result = _create_draft(payload)
            else:
                result = _delete_draft(payload)
            self._send_json(200, result)
        except Exception as e:  # noqa: BLE001
            self._send_json(500, {"ok": False, "error": str(e)})


def serve():
    mode = "cloudcall(开放接口服务,免鉴权)" if config.WX_CLOUDCALL else "token(appid+secret)"
    print(f"[relay] 启动 | 鉴权模式={mode} | 端口={config.PORT}", flush=True)
    if not config.WX_CLOUDCALL and not (config.WX_APPID and config.WX_APPSECRET):
        print("[relay][warn] 既未开启云调用也未配置 WX_APPID/WX_APPSECRET，/material、/draft 调微信会失败", flush=True)
    if not config.RELAY_API_KEY:
        print("[relay][warn] RELAY_API_KEY 未设置，写接口对外公开，任何人可调用！", flush=True)
    httpd = ThreadingHTTPServer(("0.0.0.0", config.PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    serve()
