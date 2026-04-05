# astrbot-plugin-multi-filter

AstrBot 群聊静音过滤插件：

- 支持按群配置白名单
- 支持按群配置黑名单（优先级高于白名单）
- 支持按群配置唤醒条件
- 支持多唤醒条件同时作用（any/all）
- 未命中条件时可完全拦截（不进入后续命令/插件处理）
- 内置本地 Web 管理页面（token 登录 + Cookie 会话鉴权）
- 支持聊天命令随时开启/关闭管理页面

> 说明: 本插件当前默认面向 QQ 群场景，白名单/黑名单中的“用户标识”明确指 QQ号（字符串）。

## 功能概览

### 1. 群消息过滤

- 仅处理群消息
- 可过滤机器人自身消息
- 每个群独立配置

### 2. 白名单机制

- 每个群都有独立白名单（QQ号字符串列表）
- 不在白名单内直接拦截

### 3. 黑名单机制

- 每个群都有独立黑名单（QQ号字符串列表）
- 黑名单优先级高于白名单和唤醒条件，命中后直接拦截

### 4. 唤醒条件

支持单唤醒条件与多唤醒条件：

- always: 白名单用户的任意消息放行
- keyword: 消息包含任意关键词
- prefix: 消息前缀匹配
- mention: 消息中 @ 机器人
- regex: 正则匹配消息文本

多条件模式：

- any: 任一规则命中即放行
- all: 所有规则都命中才放行

### 5. 管理页面与 API

- 监听地址: 127.0.0.1:端口
- 页面地址: /
- REST API: /api/groups, /api/group, /api/settings

### 6. 可控启停（安全）

支持在聊天中控制管理页面：

- /开启过滤器管理
- /关闭过滤器管理
- /过滤器管理状态
- /设置过滤器管理端口 8010

### 7. 数据持久化

- 配置文件原子写入
- SQLite 持久化群配置
- 启用 WAL + busy_timeout
- 缓存与数据库同步更新
- 默认写入 AstrBot 用户目录: `~/.astrbot/data/plugins/astrbot_plugin_multi_filter/`
- 插件更新后自动复用历史配置；旧目录存在数据时会自动迁移

## 项目结构

```text
.
├── main.py                      # AstrBot 插件入口
├── multi_filter/
│   ├── __init__.py
│   ├── plugin.py                # 插件主类 + 聊天命令
│   ├── config_store.py          # config.json 读写
│   ├── store.py                 # SQLite + 缓存
│   ├── models.py                # 数据模型
│   ├── event_logic.py           # 消息判定逻辑
│   ├── web.py                   # Web 服务 + API
│   └── admin_page.py            # 内嵌管理页 HTML
└── metadata.yaml
```

## 安装与加载

1. 将本插件目录放入 AstrBot 插件目录。
2. 启动 AstrBot，确认插件被正常加载。
3. 首次运行会自动生成 config.json。

## 配置说明

首次运行自动生成 config.json，默认示例：

```json
{
  "web_port": 8010,
  "web_token": "<首次启动自动生成>",
  "web_allow_external_access": false,
  "web_auto_start": false,
  "db_path": "multi_filter.db",
  "default_action": "allow"
}
```

字段说明：

- web_port: 管理页端口
- web_token: 管理页鉴权 token
- web_allow_external_access: 是否允许外网访问管理页
- web_auto_start: 插件启动时是否自动开启管理页
- db_path: SQLite 路径（相对路径默认在插件目录下）
- default_action:
  - allow: 未配置群默认放行
  - silent: 未配置群默认拦截

## 使用方式

### 1. 启停管理页

在聊天中发送：

- /开启过滤器管理
- /关闭过滤器管理
- /过滤器管理状态

### 2. 设置管理端口

在聊天中发送：

```text
/设置过滤器管理端口 8010
```

若管理页已运行，会尝试自动重启到新端口。

### 3. 访问管理页面

```text
http://127.0.0.1:8010/
```

打开页面后输入 `web_token` 登录，登录成功后会使用 HttpOnly Cookie 维持会话。

如果开启了 `web_allow_external_access`，管理页会监听 `0.0.0.0`，这时请使用服务器的 IP 或域名访问，而不是 `127.0.0.1`。

### 4. 页面内可管理内容

- 群配置新增/删除
- 启用开关
- 白名单编辑（QQ号）
- 黑名单编辑（QQ号）
- 唤醒类型与唤醒值（always / keyword / prefix / mention / regex）
- 高级多规则输入（每行 `type:value`，支持 `keyword|regex` 多类型）
- 多规则匹配模式 any / all

## API 说明

页面管理操作采用登录会话（Cookie）鉴权。

### GET /

返回管理页面。

### GET /api/groups

返回已配置群列表。

### GET /api/group?group_id=xxx

返回某群配置。

### POST /api/group

创建或更新群配置。

请求体示例：

```json
{
  "group_id": "123456",
  "enabled": true,
  "whitelist": ["10001", "10002"],
  "blacklist": ["20001", "20002"],
  "wake_type": "prefix",
  "wake_value": "/",
  "wake_mode": "any",
  "wake_rules": [
    {"type": "prefix", "value": "/"},
    {"type": "keyword", "value": ["帮助", "查询"]}
  ]
}
```

字段说明：

- blacklist: 黑名单列表，命中即拦截
- wake_mode: 多唤醒规则模式，any 或 all
- wake_rules: 多唤醒规则数组，规则结构为 {"type":"...","value":...}

### DELETE /api/group?group_id=xxx

删除某群配置。

### GET /api/settings

读取全局设置。

### POST /api/settings

更新全局设置。

请求体示例：

```json
{
  "web_port": 8010,
  "web_token": "your-strong-token",
  "web_allow_external_access": true,
  "web_auto_start": false
}
```

## 本地验证建议

### 快速联通验证

1. 先发送 /开启过滤器管理
2. 浏览器打开管理页
3. 页面新增一个测试群并保存
4. 刷新后确认配置仍存在

### 定位问题（新增日志能力）

已内置前后端联动日志，建议按下述方式排查“按钮无响应/保存失败”等问题：

1. 管理页开启前端调试

```text
http://127.0.0.1:8010/?debug=1
```

打开浏览器控制台后可看到 `[multi_filter][ui]` 日志，包含：

- 按钮触发节点（如 addGroup begin / end）
- API 请求与响应状态
- 后端返回的 trace_id

1. 对照后端日志

后端会输出 `[multi_filter][web][trace_id]` 日志，包含：

- 请求开始（method/path/query_keys）
- 请求结束（status/ok/cost_ms）
- 群配置更新、删除、全局设置更新等关键行为

通过同一个 trace_id 即可快速串联一次请求的全链路。

### 持久化验证

1. 保存群配置
2. 重启 AstrBot
3. 再次打开页面确认配置仍在

### 过滤行为验证

建议按以下矩阵测试：

- 白名单外用户发言 -> 拦截
- 白名单内但不满足唤醒条件 -> 拦截
- 白名单内且满足唤醒条件 -> 放行
- enabled=false -> 放行
- 未配置群 + default_action=allow -> 放行
- 未配置群 + default_action=silent -> 拦截
- 白名单为空 -> 不启用白名单限制
- 黑名单为空 -> 不启用黑名单拦截

### 匹配规则输入说明

- keyword: 值支持逗号、分号、换行分隔多个关键词
- prefix: 值支持逗号、分号、换行分隔多个前缀
- mention: 无需值
- always: 无需值
- regex: 建议一行一个正则；高级规则中可写多行
- 高级规则支持多类型: `keyword|regex:你好,^/help`

### 脱离 AstrBot 的自测

仓库里提供了一个独立自测脚本，可以在不启动 AstrBot 的情况下先验证核心功能：

```bash
python dev_self_test.py
```

这个脚本会自动：

- 注入 AstrBot 依赖的最小 mock
- 初始化临时 SQLite 数据库
- 验证黑名单、白名单、多唤醒规则
- 启动本地 Web 服务并测试 API
- 校验数据库落盘后的持久化结果

如果脚本最后输出 `All local self-tests passed.`，说明核心功能在当前 Python 环境里可以正常跑通。

## 安全建议

1. `web_token` 请妥善保存，不要在群聊、公网文档或截图中泄露。
2. 管理页仅绑定 127.0.0.1，不要做端口公网映射。
3. 不使用时关闭管理页（/关闭过滤器管理）。
4. 定期备份 config.json 与 SQLite 数据库。
5. token 泄露后立即更新 token 并重启管理页。

## 常见问题

### Q1: 页面打不开

- 先用 /过滤器管理状态 查看是否运行
- 确认端口是否被占用
- 确认已在登录页输入正确 token

### Q2: 设置已保存但访问异常

- 端口或 token 修改后，建议关闭再开启管理页

### Q3: IDE 报 astrbot.api 无法解析

这是本地开发环境缺少 AstrBot 依赖时的静态提示，通常不影响在 AstrBot 运行环境中加载插件。

## 参考

- AstrBot 仓库: [https://github.com/AstrBotDevs/AstrBot](https://github.com/AstrBotDevs/AstrBot)
- AstrBot 插件开发文档（中文）: [https://docs.astrbot.app/dev/star/plugin-new.html](https://docs.astrbot.app/dev/star/plugin-new.html)
- AstrBot 插件开发文档（英文）: [https://docs.astrbot.app/en/dev/star/plugin-new.html](https://docs.astrbot.app/en/dev/star/plugin-new.html)
