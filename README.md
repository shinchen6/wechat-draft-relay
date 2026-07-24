# wechat-draft-relay

部署在 **微信云托管** 上的开源服务，作为本地脚本调用公众号草稿接口的**纯代理**。
利用官方「开放接口服务（云调用）」免鉴权调用公众号接口——本地脚本无需固定 IP、无需公众号 appid/secret。

- 客户端（skill）负责写稿、把 Markdown 转成微信图文 HTML、处理图片；
- relay 把内容转交给微信接口（`/cgi-bin/material/add_material` 上传素材、`/cgi-bin/draft/add` 建草稿、`/cgi-bin/draft/delete` 删草稿）；
- 另外提供**草稿箱查询类接口**：列表 / 回读 / 计数 / 修改 / 开关，均已实测可用（云调用）；
- relay 零三方依赖，只依赖 Python 标准库。

## 支持的接口（个人订阅号 · 云调用实测可用）

| 微信接口 | relay 端点 | 说明 |
| --- | --- | --- |
| `material/add_material` | `POST /material` | 上传图片素材（封面 / 正文插图） |
| `draft/add` | `POST /draft` | 创建草稿 |
| `draft/delete` | `POST /draft-delete` | 删除草稿 |
| `draft/batchget` | `POST /draft-list` | 草稿列表（元信息） |
| `draft/get` | `POST /draft-get` | 回读单篇草稿 |
| `draft/count` | `POST /draft-count` | 草稿总数 |
| `draft/update` | `POST /draft-update` | 修改草稿 |
| `draft/switch` | `POST /draft-switch` | 草稿箱/发布开关状态 |

此外，relay 提供通用代理 `POST /cgi-bin/<path>`，可原样转发**任意已配置且账号有权限**的接口路径。个人订阅号下 `material/get_material`、`material/batchget_material`、`material/del_material`、`material/get_materialcount` 同样可用，可用该代理调用。

## 范围与限制

本工具面向**个人订阅号 + 云调用（开放接口服务）**场景。实测确认：仅 `draft/*` 全套与 `material/*` 可用。

**不能**通过云调用完成的（个人账号限制，非工具缺陷）：

- **发表文章**：`freepublish/*` 返回 `48001`（2025-07 起个人 / 未认证账号被回收发布能力），需后台手动「发表」。
- **留言 / 数据统计**：`comment/*`、`datacube/*` 个人订阅号无权限（`48001` / 配置后才可达）。
- **菜单 / 粉丝 / 标签 / 二维码 / 短链**：`menu/*`、`user/*`、`tags/*`、`qrcode/create`、`shorturl` 需账号具备对应权限并在「微信令牌」配置中加入路径。
- **`material/add_news`**（新建永久图文素材）：微信已对**新注册公众号**下线，返回 `45106`，勿依赖。

认证服务号 / 已认证企业号可按需在「微信令牌」权限配置中加入更多路径，再通过 `/cgi-bin/<path>` 代理调用。

## 架构

```
本地写稿脚本 / 诊断脚本 (skill)
   │  写接口: POST /material  POST /draft  POST /draft-delete   ─┐
   │  查接口: POST /draft-list /draft-get /draft-count /draft-update /draft-switch ─┤→ 微信接口（云调用免鉴权）
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
   - `/cgi-bin/draft/batchget`、`/cgi-bin/draft/get`、`/cgi-bin/draft/count`、`/cgi-bin/draft/update`、`/cgi-bin/draft/switch`
   - （可选）`/cgi-bin/material/get_material`、`/cgi-bin/material/batchget_material`、`/cgi-bin/material/del_material`、`/cgi-bin/material/get_materialcount`
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

| 端点              | 对应微信接口        | 请求体（JSON）要点                                | 云调用 |
| ----------------- | ------------------- | ------------------------------------------------- | ----- |
| `POST /draft-list`   | `draft/batchget`    | `{"offset":0,"count":20,"no_content":1}`          | ✅ |
| `POST /draft-get`    | `draft/get`         | `{"media_id":"..."}`                              | ✅ |
| `POST /draft-count`  | `draft/count`       | `{}`                                               | ✅ |
| `POST /draft-update` | `draft/update`      | `{"media_id":"...","index":0,"articles":{...}}`   | ✅ |
| `POST /draft-switch` | `draft/switch`      | `{}` 查状态 / `{"status":1}` 开关                  | ✅ |

### `POST /cgi-bin/<path>`（高级 / 调试用）

通用云调用代理：原样转发到 `api.weixin.qq.com/<path>`，返回 `{"http_status":..., "body":...}`。
仅转发**已配置且账号有权限**的路径；个人订阅号实测仅 `draft/*` + `material/*` 可达。

## 错误码

| errcode           | 含义                | 处理                       |
| ----------------- | ----------------- | ------------------------ |
| `41001`           | 云调用未注入凭证          | 确认已开启「开放接口服务」开关并**重建版本** |
| `48001`           | 接口未授权             | 「微信令牌」权限配置中加入对应接口路径；或账号无该接口权限 |
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
