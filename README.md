# wechat-draft-relay

部署在 **微信云托管** 上的开源服务，作为本地脚本调用公众号草稿接口的**纯代理**。  
利用官方「开放接口服务（云调用）」免鉴权调用公众号接口——本地脚本无需固定 IP、无需公众号 appid/secret。

- 客户端（skill）负责写稿、把 Markdown 转成微信图文 HTML、处理图片；
- relay 只做一件事：把内容转交给微信接口（`/cgi-bin/material/add_material` 上传素材、`/cgi-bin/draft/add` 建草稿、`/cgi-bin/draft/delete` 删草稿）。
- relay 零三方依赖，只依赖 Python 标准库。

## 架构

```
本地写稿脚本 (skill)
   │  POST /material (图片 base64)  ─┐
   │  POST /draft  (title, html, thumb) ─┤→ 微信接口（云调用免鉴权）
   ▼                                    │
部署在微信云托管的 relay（本仓库）
        （默认公网访问地址，靠 RELAY_API_KEY 保护）
```

relay **不解析 Markdown**，不生成 HTML——这些都在客户端完成。

## 部署

1. **代码来源**：Fork 本仓库后授权 GitHub 拉取，或下载源码以「本地代码包」上传（≤2MiB）。
2. **开启开放接口服务**：云托管控制台开启「开放接口服务」开关；在「微信令牌」权限配置中加入：
   - `/cgi-bin/material/add_material`
   - `/cgi-bin/draft/add`
   - `/cgi-bin/draft/delete`（删除草稿功能需要）
3. **环境变量**：
   - `RELAY_API_KEY`：必填，relay 自身访问密钥，用于保护公网接口。
   - `WX_APPID` / `WX_APPSECRET`：**留空**。云托管绑定公众号并开启开放接口服务后，平台自动注入鉴权，无需填写。
   - `WX_CLOUDCALL=1`：可选，强制云调用模式（即使误填了 appid/secret 也会被忽略）。
   - `PORT`：默认 `8000`（与云托管「容器监听端口」一致）。
   - `DEFAULT_AUTHOR`：可选，草稿默认作者署名。

> 入站地址用云托管控制台「服务详情 → 默认公网访问地址」给出的域名，无需固定 IP 白名单。

## API

所有写接口都需在请求头带 `X-API-Key: <RELAY_API_KEY>`（未配置 `RELAY_API_KEY` 时不校验）。

### `GET /health`

```json
{ "ok": true, "mode": "cloudcall" }
```

### `POST /material`

请求体（JSON）：

```json
{ "name": "img/body1.png", "data_b64": "<图片 base64>" }
```

返回：

```json
{ "media_id": "...", "url": "https://mmbiz.qpic.cn/..." }
```

### `POST /draft`

请求体（JSON）：

```json
{
  "title": "文章标题",
  "content_html": "<section>...</section>",
  "thumb_media_id": "<封面素材 media_id>",
  "author": "可选",
  "digest": "可选摘要"
}
```

返回：

```json
{ "media_id": "草稿 media_id" }
```

### `POST /draft-delete`

删除指定草稿（需先在「微信令牌」权限配置中加入 `/cgi-bin/draft/delete`）。

请求体（JSON）：

```json
{ "media_id": "要删除的草稿 media_id" }
```

返回（微信原始响应）：

```json
{ "errcode": 0, "errmsg": "ok" }
```

## 错误码

| errcode           | 含义                | 处理                       |
| ----------------- | ----------------- | ------------------------ |
| `41001`           | 云调用未注入凭证          | 确认已开启「开放接口服务」开关并**重建版本** |
| `48001` / `85107` | 接口未授权             | 「微信令牌」权限配置中加入对应接口路径      |
| `40164`           | IP 不在白名单          | 非云托管部署才需；云托管免此步（用云调用模式）  |
| `invalid api key` | 缺 / 错 `X-API-Key` | 检查客户端注入的 `RELAY_API_KEY` |
| `500`             | relay 内部 / 微信返回错误 | 响应体 `error` 字段含具体原因      |

## 本地调试

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # 空文件，relay 无三方依赖
cp .env.example .env              # 填 RELAY_API_KEY、WX_CLOUDCALL=1
python -m app.main
```
