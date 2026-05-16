# X Capture Session Management Requirements

# 需求总目标
让浏览器扩展把“开始监听”到“停止监听”视为一次抓取会话，并按会话管理本地数据。每次会话单独保存 raw JSON、tweet JSON、正文图片和错误记录。扩展 popup 显示历史会话列表，并允许用户删除某一次会话的全部本地数据。

# 事实前提

- 【前提 A1】旧的 `captures/raw/`、`captures/tweets/`、`captures/images/`、`captures/errors/` 是结构解析阶段数据，不迁移、不删除、不显示为生产会话。
- 【前提 A2】新版本开始，生产抓取数据写入 `captures/sessions/<session_id>/`。
- 【前提 A3】一次会话从用户点击“开始监听”开始，到用户点击“停止监听”、tab 关闭、离开 X 页面或 debugger detach 结束。
- 【前提 A4】删除会话只删除 `captures/sessions/<session_id>/`，不得删除 `captures/` 根目录或旧解析数据。
- 【前提 A5】扩展仍不发送外部网络请求；会话管理只通过 Native Messaging Host 读写本地文件。
- 【前提 A6】打开本地目录只调用操作系统文件管理器；扩展不直接访问本地文件系统路径，路径校验由 Native Messaging Host 执行。
- 【前提 A7】可见帖子导出使用本地 `scripts/export_visible_tweets.py` 的解析逻辑，只读取 session 目录内已保存的 JSON 和图片，不下载缺失媒体。
- 【前提 A8】纯语料导出写入 `visible_tweets_pure.txt`，每条记录只包含发言人、时间、回复/引用关系（如果有）和正文。

# 入口条件树

- `1` 如果用户点击 popup 的“开始监听”，那么扩展为当前 X tab 创建新会话。
  - `1-1` 如果当前 tab 是 X 页面，那么扩展请求 native host 创建 `session_id` 和会话目录。
  - `1-2` 否则扩展显示“当前页面不是 X”，不创建会话。
- `2` 如果 native host 创建会话成功，那么扩展 attach debugger 并启用 Network。
  - `2-1` 如果 attach 和 `Network.enable` 成功，那么会话状态为“监听中”。
  - `2-2` 否则扩展关闭会话、detach debugger，并显示失败原因。
- `3` 如果用户打开 popup，那么扩展读取当前 tab 状态和 native host 会话列表。
  - `3-1` 如果 native host 返回会话列表，那么 popup 显示历史抓取记录。
  - `3-2` 否则 popup 显示会话列表读取失败原因。

# 数据流条件树

- `4` 如果监听中保存 raw JSON、tweet JSON、图片或错误记录，那么扩展给 native host 消息附加当前 `session_id`。
  - `4-1` 如果消息包含有效 `session_id`，那么 native host 写入 `captures/sessions/<session_id>/` 下的对应子目录。
  - `4-2` 否则 native host 使用旧兼容路径写入 `captures/raw|tweets|images|errors`。
- `5` 如果 native host 写入会话数据成功，那么 native host 更新该会话的 `manifest.json`。
  - `5-1` 如果写入 raw JSON 成功，那么 `counters.rawJson += 1`。
  - `5-2` 如果写入 tweet JSON 成功，那么 `counters.tweets += 1`。
  - `5-3` 如果写入新图片成功，那么 `counters.images += 1`。
  - `5-4` 如果写入错误记录成功，那么 `counters.errors += 1`。

# 主流程条件树

- `6` 如果用户点击“停止监听”，那么扩展 detach debugger 并关闭当前会话。
  - `6-1` 如果当前 tab 有活动会话，那么扩展发送 `close_session` 给 native host。
  - `6-2` 否则扩展只刷新状态为“未监听”。
- `7` 如果 native host 收到 `close_session`，那么 native host 写入 `ended_at`、`status: "closed"` 和最终计数。
  - `7-1` 如果 `manifest.json` 写入成功，那么 native host 在 session 根目录生成 `visible_tweets.html`、`visible_tweets.csv`、`visible_tweets.jsonl`、`visible_tweets_pure.txt` 和 `summary.json`。
  - `7-2` 否则返回写入失败原因。
  - `7-3` 如果导出成功，那么 native host 将导出文件路径和记录数写入 manifest 的 `export` 字段，并返回关闭后的会话摘要。
  - `7-4` 如果导出失败，那么 native host 将导出错误写入 manifest 的 `export` 字段，但不回滚已关闭的会话。
- `8` 如果用户点击某条历史会话的“删除”，那么 popup 弹出确认。
  - `8-1` 如果用户确认删除，那么扩展发送 `delete_session(session_id)` 给 native host。
  - `8-2` 否则取消删除，不修改任何文件。
- `9` 如果 native host 收到 `delete_session`，那么 native host 校验目标目录。
  - `9-1` 如果目标路径位于 `captures/sessions/` 内且存在，那么删除该 session 目录。
  - `9-2` 如果目标路径不存在，那么返回“已不存在”并刷新列表。
  - `9-3` 如果 `session_id` 试图逃逸目录，那么拒绝删除并返回错误。

# 界面与交互条件树

- `10` 如果 popup 显示活动会话，那么显示当前 `session_id` 和当前会话计数。
- `11` 如果 popup 显示历史会话，那么每条会话显示开始时间、结束时间、来源 URL、raw/tweets/images/errors 计数和删除按钮。
- `12` 如果会话状态是 `active`，那么删除按钮禁用，避免删除仍在写入的目录。
- `13` 如果删除成功，那么 popup 从列表中移除该会话并显示刷新后的列表。
- `14` 如果用户点击某条历史会话的“打开目录”，那么 popup 发送 `open_session_directory(session_id)` 给 native host。
  - `14-1` 如果 `session_id` 对应的目录位于 `captures/sessions/` 内且存在，那么 native host 先确保该目录下存在 `visible_tweets.html` 等导出文件。
  - `14-2` 如果导出文件生成或确认成功，那么 native host 调用操作系统文件管理器打开该目录，并向 popup 返回打开的路径。
  - `14-3` 否则 native host 拒绝打开并返回错误原因。
- `15` 如果用户点击某条历史会话的“手动生成”，那么 popup 发送 `generate_session_export(session_id)` 给 native host。
  - `15-1` 如果 `session_id` 对应的目录位于 `captures/sessions/` 内且存在，那么 native host 重新生成 `visible_tweets_pure.txt`。
  - `15-2` 如果重新生成成功，那么 native host 更新 manifest 的 `export` 字段，popup 刷新会话列表。
  - `15-3` 否则 native host 返回错误原因，popup 显示错误。

# 例外与边界条件树

- `16` 如果 service worker 被 Chrome 回收导致活动会话未正常关闭，那么 native host 的 manifest 保留 `status: "active"` 和最后更新时间，后续列表仍显示该会话。
- `17` 如果用户关闭 tab 或离开 X 页面，那么扩展尽力关闭会话；如果关闭失败，popup 下次读取列表时仍可看到该会话。
- `18` 如果同一个 tweet 在同一个会话内多次出现，那么仍按 tweet id 覆盖整理 JSON；manifest 计数反映保存消息次数或最终关闭计数。

# ERROR 汇总

无。
