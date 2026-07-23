"""微信服务端调用：access_token 缓存 + 素材库上传 + 草稿创建。

零三方依赖：仅用 Python 标准库 urllib（不再依赖 httpx）。

两种鉴权模式：
- 云调用（开放接口服务）模式（config.WX_CLOUDCALL=True）：
  部署在微信云托管、已开启「开放接口服务」开关并配置接口权限时，
  容器内直接以 HTTP 请求 api.weixin.qq.com，平台自动注入鉴权，无需 access_token。
- token 模式（默认本地 / 非云托管）：
  用 WX_APPID / WX_APPSECRET 换取 access_token，再携带调用接口。
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config

_TOKEN_CACHE: dict = {"token": None, "exp": 0}

# 云调用模式用 HTTP（性能更好，平台侧旁加载会拦截并注入鉴权）；
# token 模式用 HTTPS 并携带 access_token。
_BASE = "http://api.weixin.qq.com" if config.WX_CLOUDCALL else "https://api.weixin.qq.com"

# 常见错误码 → 人话提示，方便排障
_ERR_HINTS = {
    40013: "（appid 无效；token 模式请检查 WX_APPID）",
    40164: "（调用 IP 不在白名单；非云托管部署需到公众号后台「IP白名单」加本机出口 IP）",
    41001: "（云调用模式：确认已在云托管控制台开启「开放接口服务」开关并重建版本）",
    48001: "（接口未授权；云调用需在「微信令牌」权限配置中加入该接口路径，如 /cgi-bin/draft/add、/cgi-bin/draft/delete）",
    85009: "（草稿接口频率受限，稍后重试）",
}


def using_cloudcall() -> bool:
    return config.WX_CLOUDCALL


def _url(path: str, params: dict | None = None) -> str:
    u = _BASE + path
    if params:
        u += "?" + urllib.parse.urlencode(params)
    return u


def _request_json(url: str, *, data: bytes | None = None, headers: dict | None = None,
                  method: str = "POST", timeout: int = 30) -> dict:
    """发请求并解析微信返回的 JSON。HTTPError 也尽量读回 body 转成 dict。"""
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:  # 微信有时用非 200 返回错误体
        raw = e.read()
        try:
            return json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            raise RuntimeError(f"微信接口 HTTP {e.code}: {raw[:200]!r}")
    return json.loads(raw.decode("utf-8", "replace"))


def _multipart_body(files: dict, boundary: str) -> tuple[bytes, str]:
    """files: {name: (filename, bytes, content_type)} → (body, content-type)"""
    parts = []
    for name, (filename, data, ctype) in files.items():
        parts.append(f"--{boundary}\r\n".encode("utf-8"))
        parts.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8")
        )
        parts.append(f"Content-Type: {ctype}\r\n\r\n".encode("utf-8"))
        parts.append(data if isinstance(data, (bytes, bytearray)) else bytes(data))
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    return body, f"multipart/form-data; boundary={boundary}"


def get_access_token() -> str:
    """token 模式：用 appid+secret 换取 access_token，本地缓存到过期前 60s。"""
    if config.WX_CLOUDCALL:
        raise RuntimeError(
            "当前为云调用模式，不应调用 get_access_token。"
            "请确认在微信云托管控制台开启了「开放接口服务」开关并重建版本。"
        )
    if not config.WX_APPID or not config.WX_APPSECRET:
        raise RuntimeError("token 模式缺少 WX_APPID / WX_APPSECRET")
    now = time.time()
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["exp"] > now + 60:
        return _TOKEN_CACHE["token"]
    data = _request_json(
        _url("/cgi-bin/token", {
            "grant_type": "client_credential",
            "appid": config.WX_APPID,
            "secret": config.WX_APPSECRET,
        }),
        method="GET",
        timeout=20,
    )
    if "access_token" not in data:
        raise RuntimeError(f"获取 access_token 失败: {data}")
    _TOKEN_CACHE["token"] = data["access_token"]
    _TOKEN_CACHE["exp"] = now + data.get("expires_in", 7200)
    return _TOKEN_CACHE["token"]


def _auth_params() -> dict:
    """云调用模式返回空；token 模式返回 access_token 查询参数。"""
    if config.WX_CLOUDCALL:
        return {}
    return {"access_token": get_access_token()}


def _raise(api: str, data: dict):
    hint = _ERR_HINTS.get(data.get("errcode"), "")
    raise RuntimeError(f"{api} 失败: {data} {hint}")


def upload_image(data: bytes, filename: str = "img.png") -> dict:
    """上传图片到素材库，返回 {'media_id':..., 'url': mmbiz 链接}。"""
    url = _url("/cgi-bin/material/add_material", {"type": "image", **_auth_params()})
    boundary = "wechatrelay" + str(int(time.time() * 1000))
    body, ctype = _multipart_body({"media": (filename, data, "image/png")}, boundary)
    data_json = _request_json(url, data=body, headers={"Content-Type": ctype}, timeout=30)
    if data_json.get("errcode"):
        _raise("素材上传", data_json)
    return {"media_id": data_json["media_id"], "url": data_json["url"]}


def add_draft(
    title: str,
    content_html: str,
    thumb_media_id: str,
    author: str = "",
    digest: str = "",
) -> str:
    """创建草稿，返回 media_id。"""
    body = {
        "articles": [
            {
                "title": title,
                "author": author,
                "digest": digest,
                "content": content_html,
                "thumb_media_id": thumb_media_id,
                "need_open_comment": 1,
                "only_fans_can_comment": 0,
            }
        ]
    }
    data = _request_json(
        _url("/cgi-bin/draft/add", _auth_params()),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if data.get("errcode"):
        _raise("草稿创建", data)
    return data["media_id"]


def delete_draft(media_id: str) -> dict:
    """删除草稿，返回微信原始响应（成功为 {'errcode':0,'errmsg':'ok'}）。"""
    if not media_id:
        raise ValueError("media_id 不能为空")
    body = {"media_id": media_id}
    data = _request_json(
        _url("/cgi-bin/draft/delete", _auth_params()),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if data.get("errcode"):
        _raise("草稿删除", data)
    return data


# ── 查询类接口（诊断用）──────────────────────────────────────────────
# 统一返回微信原始响应（含 errcode/errmsg），由调用方判断是否成功；
# 不在此层 _raise，便于把错误原样透传给诊断端展示。

def _raw_post(path: str, payload: dict) -> dict:
    return _request_json(
        _url(path, _auth_params()),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=30,
    )


def list_drafts(offset: int = 0, count: int = 20, no_content: int = 1) -> dict:
    """草稿列表。no_content=1 时只取元信息（media_id/标题/更新时间），不拉正文。"""
    return _raw_post("/cgi-bin/draft/batchget",
                     {"offset": offset, "count": count, "no_content": no_content})


def get_draft(media_id: str) -> dict:
    """回读单篇草稿完整内容（正文 HTML / 摘要 / 封面）。"""
    if not media_id:
        raise ValueError("media_id 不能为空")
    return _raw_post("/cgi-bin/draft/get", {"media_id": media_id})


def count_drafts() -> dict:
    """草稿总数。"""
    return _raw_post("/cgi-bin/draft/count", {})


def update_draft(media_id: str, articles: dict, index: int = 0) -> dict:
    """修改草稿（标题/正文/封面/摘要）。articles 为单篇图文 dict。"""
    if not media_id:
        raise ValueError("media_id 不能为空")
    if not articles:
        raise ValueError("articles 不能为空")
    return _raw_post("/cgi-bin/draft/update",
                     {"media_id": media_id, "index": index, "articles": articles})


def set_draft_switch(status: int | None = None) -> dict:
    """草稿箱/发布开关：status=0 关 / 1 开；不传 status 则返回当前开关状态。"""
    if status is None:
        return _raw_post("/cgi-bin/draft/switch", {})
    return _raw_post("/cgi-bin/draft/switch", {"status": status})


def list_published(offset: int = 0, count: int = 20) -> dict:
    """已发布消息列表（freepublish/batchget）。item 含 msg_data_id / 标题 / 永久链接。"""
    return _raw_post("/cgi-bin/freepublish/batchget", {"offset": offset, "count": count})


def get_user_summary(begin: str, end: str) -> dict:
    """用户增减数据（datacube/getusersummary）。begin/end: YYYY-MM-DD，最长 7 天窗口。"""
    return _raw_post("/cgi-bin/datacube/getusersummary",
                     {"begin_date": begin, "end_date": end})


def get_user_read(begin: str, end: str) -> dict:
    """图文阅读关键数据（datacube/getuserread）。最长 3 天窗口。"""
    return _raw_post("/cgi-bin/datacube/getuserread",
                     {"begin_date": begin, "end_date": end})


def get_article_total(begin: str, end: str) -> dict:
    """图文群发总数据（datacube/getarticletotal）。"""
    return _raw_post("/cgi-bin/datacube/getarticletotal",
                     {"begin_date": begin, "end_date": end})


def list_comments(msg_data_id: str, index: int = 0, begin: int = 0, count: int = 20) -> dict:
    """留言列表（comment/list）。msg_data_id 来自 freepublish/batchget 的 item.msg_data_id。"""
    if not msg_data_id:
        raise ValueError("msg_data_id 不能为空")
    return _raw_post("/cgi-bin/comment/list",
                     {"msg_data_id": msg_data_id, "index": index, "begin": begin, "count": count})
