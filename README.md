# wechat-draft-relay

部署在 **微信云托管** 上的开源服务，作为本地脚本调用公众号草稿接口的**纯代理**。  
利用官方「开放接口服务（云调用）」免鉴权调用公众号接口——本地脚本无需固定 IP、无需公众号 appid/secret。

- 客户端（skill）负责写稿、把 Markdown 转成微信图文 HTML、处理图片；
- relay 把内容转交给微信接口（`/cgi-bin/material/add_material` 上传素材、`/cgi-bin/draft/add` 建草稿、`/cgi-bin/draft/delete` 删草稿）；
- 另外提供**查询类接口**（草稿列表/回读/计数、已发布列表、用户增减、图文阅读、留言），用于草稿箱全生命周期诊断；
- relay 零三方依赖，只依赖 Python 标准库。

## 架构

```
本地写稿脚本 / 诊断脚本 (skill)
   │  写接口: POST /material  POST /draft  POST /draft-delete   ─┐
   │  查接口: POST /draft-list /published-list /stats-* /comment-list ─┤→ 微信接口（云调用免鉴权）
   ▼                                                          │
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
   - 查询/诊断接口按需加入：`/cgi-bin/draft/batchget`、`/cgi-bin/draft/get`、`/cgi-bin/draft/count`、`/cgi-bin/draft/update`、`/cgi-bin/draft/switch`、`/cgi-bin/freepublish/batchget`、`/cgi-bin/datacube/getusersummary`、`/cgi-bin/datacube/getuserread`、`/cgi-bin/datacube/getarticletotal`、`/cgi-bin/comment/list`
   - ⚠️ `freepublish` / `datacube` / `comment` 三类接口**实测确认不支持云调用**（freepublish→`48001`、datacube→`404`、comment→`48001`）：需 relay 切换到 token 模式（填 `WX_APPID`/`WX_APPSECRET`，回到 IP 白名单）才能用。`draft/*` 全套 + `material` 均支持云调用（已验证 `draft/add`、`draft/batchget`、`draft/get`、`draft/count`）。
   - 改完权限后务必**重建版本**（开放接口服务开关「开关前建的版本不生效」）。
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

### 查询类接口（诊断用）

以下接口原样透传微信响应（含 `errcode`/`errmsg`），由客户端判断是否成功。请求头同样需 `X-API-Key`。

| 端点              | 对应微信接口                      | 请求体（JSON）要点                                  |
| ----------------- | ------------------------------- | ------------------------------------------------- |
| `POST /draft-list`   | `draft/batchget`                | `{"offset":0,"count":20,"no_content":1}`          |
| `POST /draft-get`    | `draft/get`                     | `{"media_id":"..."}`                              |
| `POST /draft-count`  | `draft/count`                   | `{}`                                               |
| `POST /draft-update` | `draft/update`                  | `{"media_id":"...","index":0,"articles":{...}}`   |
| `POST /draft-switch` | `draft/switch`                  | `{}` 查状态 / `{"status":1}` 开关                  |
| `POST /published-list` | `freepublish/batchget`       | `{"offset":0,"count":20}`                          |
| `POST /stats-user`    | `datacube/getusersummary`     | `{"begin_date":"2026-07-16","end_date":"2026-07-22"}`（≤7天） |
| `POST /stats-article` | `datacube/getuserread`        | `{"begin_date":"...","end_date":"..."}`（≤3天）   |
| `POST /comment-list`  | `comment/list`                 | `{"msg_data_id":"...","index":0,"begin":0,"count":20}` |

> `published-list` 返回的 `msg_data_id` 可作为 `comment-list` 的 `msg_data_id` 查询某篇文章留言。
> `stats-*` 日期窗口有限制（用户增减 ≤7 天、图文阅读 ≤3 天），跨更长区间需多次调用拼接。

> ✅ **已实测可用（云调用）**：`/draft-list`、`/draft-get`、`/draft-count`、`/draft-update`、`/draft-switch` 与写接口（`/material`、`/draft`、`/draft-delete`）。
> ❌ **实测不可用（云调用，需 token 模式）**：`/published-list`（freepublish→48001）、`/stats-user`、`/stats-article`（datacube→404）、`/comment-list`（comment→48001）。

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
cp .env.example .env              # 填 RELAY_API_KEY、WX_CLOUDCALL=1
python -m app.main
```

relay 零三方依赖（仅 Python 标准库），无需 `pip install` 任何包。
