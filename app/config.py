"""Relay 配置：全部来自环境变量，开源部署零硬编码密钥。"""
import os

# ── 微信公众号凭证（仅「本地 / 非云托管」token 模式需要）─────────────
# 部署在微信云托管并开启「开放接口服务」时，无需填写这两项：
# 云调用会由平台自动注入鉴权，容器直接请求 api.weixin.qq.com 即可。
# 本地调试、或部署在其它平台时，才需要填 appid + secret 换取 access_token。
WX_APPID = os.environ.get("WX_APPID", "")
WX_APPSECRET = os.environ.get("WX_APPSECRET", "")

# ── 云调用（开放接口服务）模式开关 ───────────────────────────────
# 不显式设置时：同时提供了 WX_APPID + WX_APPSECRET → 走 token 模式；
# 否则（云托管内、未填凭证）→ 自动走云调用模式（http://api.weixin.qq.com，免鉴权）。
# 也可显式 WX_CLOUDCALL=1 强制开启（即使填了 appid/secret 也会被忽略）。
_wx_cloudcall_env = os.environ.get("WX_CLOUDCALL")
if _wx_cloudcall_env is None:
    WX_CLOUDCALL = not (WX_APPID and WX_APPSECRET)
else:
    WX_CLOUDCALL = _wx_cloudcall_env == "1"

# ── relay 自身访问密钥（客户端调用 /publish 时带 X-API-Key 头）────
# 云托管默认公网访问地址是平台生成的「默认域名」，任何人可访问，
# 因此务必设置 RELAY_API_KEY 保护接口（留空 = 不校验，仅限本地测试）。
RELAY_API_KEY = os.environ.get("RELAY_API_KEY", "")

# 监听端口（云托管读取容器监听端口，保持一致即可）
PORT = int(os.environ.get("PORT", "8000"))

# 作者署名（写入草稿 author 字段，可空）
DEFAULT_AUTHOR = os.environ.get("DEFAULT_AUTHOR", "")
