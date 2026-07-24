# wechat-draft-relay

部署在 **微信云托管** 的纯代理服务，利用官方「开放接口服务（云调用）」免鉴权调用公众号接口——本地无需固定 IP、无需 appid/secret。relay 零三方依赖（仅 Python 标准库）。

## 支持的接口

| 微信接口 | relay 端点 | 说明 |
| --- | --- | --- |
| `material/add_material` | `POST /material` | 上传图片素材 |
| `draft/add` | `POST /draft` | 创建草稿 |
| `draft/delete` | `POST /draft-delete` | 删除草稿 |
| `draft/batchget` | `POST /draft-list` | 草稿列表 |
| `draft/get` | `POST /draft-get` | 回读单篇草稿 |
| `draft/count` | `POST /draft-count` | 草稿总数 |
| `draft/update` | `POST /draft-update` | 修改草稿 |
| `draft/switch` | `POST /draft-switch` | 草稿箱/发布开关 |

通用代理 `POST /cgi-bin/<path>` 可转发已配置的任意接口路径。

## 部署

1. 微信云托管控制台开启「开放接口服务」，在「微信令牌」权限配置加入以下路径：
   - `/cgi-bin/material/add_material`
   - `/cgi-bin/draft/add`、`/cgi-bin/draft/delete`
   - `/cgi-bin/draft/batchget`、`/cgi-bin/draft/get`、`/cgi-bin/draft/count`、`/cgi-bin/draft/update`、`/cgi-bin/draft/switch`
   - 改完权限后**重建版本**使配置生效。
2. 环境变量：
   - `RELAY_API_KEY`：必填，relay 访问密钥。
   - `WX_APPID` / `WX_APPSECRET`：留空（云调用自动注入鉴权）。
   - `WX_CLOUDCALL=1`：可选，强制云调用模式。
   - `PORT`：默认 `8000`。

## API

所有写/查接口需请求头 `X-API-Key: <RELAY_API_KEY>`。

### `GET /health`
```json
{ "ok": true, "mode": "cloudcall" }
```

### `POST /material`
```json
{ "name": "img/body1.png", "data_b64": "<图片 base64>" }
// → { "media_id": "...", "url": "https://mmbiz.qpic.cn/..." }
```

### `POST /draft`
```json
{ "title": "标题", "content_html": "<section>...</section>", "thumb_media_id": "<封面 media_id>", "author": "可选", "digest": "可选摘要" }
// → { "media_id": "草稿 media_id" }
```

### `POST /draft-delete`
```json
{ "media_id": "要删除的草稿 media_id" }
// → { "errcode": 0, "errmsg": "ok" }
```

### 查询类
| 端点 | 对应微信接口 | 请求体 |
| --- | --- | --- |
| `POST /draft-list` | `draft/batchget` | `{"offset":0,"count":20,"no_content":1}` |
| `POST /draft-get` | `draft/get` | `{"media_id":"..."}` |
| `POST /draft-count` | `draft/count` | `{}` |
| `POST /draft-update` | `draft/update` | `{"media_id":"...","index":0,"articles":{...}}` |
| `POST /draft-switch` | `draft/switch` | `{}` 或 `{"status":1}` |

### `POST /cgi-bin/<path>`
通用云调用代理：原样转发到 `api.weixin.qq.com/<path>`，返回 `{"http_status":..., "body":...}`。

## 本地调试
```bash
python -m venv .venv && source .venv/bin/activate
cp .env.example .env   # 填 RELAY_API_KEY、WX_CLOUDCALL=1
python -m app.main
```
