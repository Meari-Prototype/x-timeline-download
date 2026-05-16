# X Timeline Local Capture Requirements

# 需求总目标

构建一个仅支持 Chrome 的浏览器扩展。用户浏览 X 时间线时，用户通过扩展图标手动开启或停止监听当前 tab。扩展使用 `chrome.debugger` 读取当前 tab 已经产生的 Chrome DevTools Protocol Network 事件和 response body，将目标 JSON 和 tweet 正文图片交给 Python 本地脚本保存到脚本同目录下的保存文件夹。

工具必须只读取和拷贝已经自然加载到浏览器中的内容。工具自身不得发送外部网络请求，不得补下载，不得重放请求，不得修改 headers/cookies，不得注入页面 JavaScript，不得使用代理，不得安装 CA，不得做 HTTPS MITM。

# 事实前提

- 【前提 A1】用户使用 Chrome 浏览器访问 X。
- 【前提 A2】扩展只支持 Chrome，不要求支持 Edge、Firefox 或其他浏览器。
- 【前提 A3】用户通过浏览器左上角扩展图标打开 popup，并在 popup 中选择是否开启监听。
- 【前提 A4】监听对象是用户开启监听时的当前 X tab。
- 【前提 A5】扩展可以请求 `debugger`、`tabs`、`storage`、`nativeMessaging` 以及 X 相关 host permissions。
- 【前提 A6】Chrome 本地显示“扩展正在调试当前 tab”的提示时，用户接受该提示。
- 【前提 A7】捕获方式使用 `chrome.debugger` 调用 CDP `Network` 域。
- 【前提 A8】扩展读取类似 F12 Network 面板的数据源，不读取 F12 UI 表格本身。
- 【前提 A9】扩展不得调用页面环境中的 `fetch`、`XMLHttpRequest` 或其他页面脚本接口。
- 【前提 A10】扩展不得向 X 或其他外部地址发送任何网络请求。
- 【前提 A11】扩展不得重放请求，不得补下载未加载资源，不得打开新 URL，不得修改请求头、cookie、UA、client hints 或缓存策略。
- 【前提 A12】扩展不得注入或 hook 页面 JavaScript。
- 【前提 A13】工具不得使用代理，不得安装本地 CA，不得做 HTTPS MITM。
- 【前提 A14】视频、音频、`.m4s` 分片、`video.twimg.com` 资源不保存。
- 【前提 A15】图片保存范围仅限 tweet 正文图片；引用推文中的正文图片也属于保存范围。
- 【前提 A16】头像、emoji、广告图、普通卡片封面、装饰资源不保存。
- 【前提 A17】保存数据格式为 JSON 文件和图片文件，不要求 SQLite。
- 【前提 A18】本地写入由 Python native host / 本地脚本完成。
- 【前提 A19】Python 脚本在自身同目录创建 `captures/` 保存文件夹，并将 JSON 和图片写入该保存文件夹。
- 【前提 A20】用户手动安装 Chrome 扩展和 Native Messaging Host。
- 【前提 A21】Native Messaging Host 的 Windows 注册由项目提供的安装脚本生成，用户手动执行该脚本。

# 入口条件树

- `1` 如果用户点击 Chrome 扩展图标，那么扩展打开 popup，显示当前 tab 的监听状态。
  - `1-1` 如果当前 tab 未监听，那么 popup 显示“开始监听”按钮，输出状态为「未监听」。
  - `1-2` 否则 popup 显示“停止监听”按钮，输出状态为「监听中」。

- `2` 如果用户点击“开始监听”，那么扩展读取当前 Chrome tab 的 `tabId` 和 URL。
  - `2-1` 如果 URL 属于 `https://x.com/*` 或 `https://twitter.com/*`，那么扩展调用 `chrome.debugger.attach` 绑定当前 `tabId`，输出状态为「attach 中」。
  - `2-2` 否则扩展拒绝 attach，popup 显示“当前页面不是 X”，输出状态为「未监听」。

- `3` 如果 `chrome.debugger.attach` 返回成功，那么扩展调用 CDP `Network.enable`，输出状态为「监听中」。
  - `3-1` 如果 `Network.enable` 返回成功，那么扩展开始接收当前 tab 的 Network 事件。
  - `3-2` 否则扩展调用 `chrome.debugger.detach`，popup 显示 Network 启用失败原因，输出状态为「未监听」。

- `4` 如果 `chrome.debugger.attach` 返回失败，那么扩展显示 attach 失败原因，输出状态为「未监听」。
  - `4-1` 如果失败原因为当前 tab 已被 DevTools 或其他 debugger 占用，那么显示“当前 tab 已被调试目标占用”。
  - `4-2` 否则显示 Chrome 返回的原始错误信息。

# 数据流条件树

- `5` 如果 CDP 收到 `Network.requestWillBeSent` 事件，那么扩展读取 `requestId`、URL、method、resource type、timestamp。
  - `5-1` 如果 URL 属于 X 相关域名集合，那么扩展创建或更新该 `requestId` 的请求元数据。
  - `5-2` 否则扩展丢弃该事件，不写入本地。

- `6` 如果 CDP 收到 `Network.responseReceived` 事件，那么扩展读取 `requestId`、URL、status、response headers、mimeType、resource type、timestamp。
  - `6-1` 如果 URL 属于 X 相关域名集合，那么扩展创建或更新该 `requestId` 的响应元数据。
  - `6-2` 否则扩展丢弃该事件，不写入本地。

- `7` 如果 CDP 收到 `Network.loadingFinished` 事件，并且该 `requestId` 已有响应元数据，那么扩展调用 `Network.getResponseBody(requestId)` 读取响应体。
  - `7-1` 如果读取成功，那么扩展进入内容分类流程。
  - `7-2` 否则扩展向 Python 本地脚本发送错误记录，输出该 request 为「body 读取失败」。

- `8` 如果响应 `content-type`、`mimeType` 或 body 内容表示 JSON，那么扩展将响应归类为 JSON 响应。
  - `8-1` 如果 body 可解析为 JSON，那么扩展向 Python 本地脚本发送 raw JSON 保存消息。
  - `8-2` 否则扩展向 Python 本地脚本发送 JSON 解析失败错误记录，不写入整理 JSON。

- `9` 如果 JSON 响应中包含 timeline、tweet、user 或 media 数据，那么扩展或本地脚本从 JSON 中提取 tweet 记录。
  - `9-1` 如果可提取 tweet id，那么写入整理后的 tweet JSON。
  - `9-2` 否则只保留 raw JSON，不写入整理后的 tweet JSON。

- `10` 如果整理后的 tweet JSON 中包含正文媒体图片 URL，那么工具将该图片 URL 加入允许保存图片集合。
  - `10-1` 如果图片属于当前 tweet 正文媒体，那么加入允许保存图片集合。
  - `10-2` 如果图片属于引用 tweet 正文媒体，那么加入允许保存图片集合。
  - `10-3` 否则不加入允许保存图片集合。

- `11` 如果响应 `content-type` 或 `mimeType` 表示图片，那么扩展判断该图片 URL 是否属于允许保存图片集合。
  - `11-1` 如果图片 URL 属于允许保存图片集合，那么扩展向 Python 本地脚本发送图片保存消息。
  - `11-2` 否则扩展丢弃该图片响应，不写入本地。

- `12` 如果响应属于视频、音频、`.m4s` 分片或 `video.twimg.com` 资源，那么扩展丢弃该响应。
  - `12-1` 如果该视频 URL 出现在 tweet JSON 中，那么只在 tweet JSON 中保留 URL 引用。
  - `12-2` 否则不记录该资源。

# 主流程条件树

- `13` 【LOOP】当监听状态为「监听中」时，扩展循环接收当前 tab 的 CDP Network 事件。
  - `13-1` 如果事件类型为 `Network.requestWillBeSent`，那么执行节点 `5`。
  - `13-2` 如果事件类型为 `Network.responseReceived`，那么执行节点 `6`。
  - `13-3` 如果事件类型为 `Network.loadingFinished`，那么执行节点 `7` 到 `12`。
  - `13-4` 如果事件类型不是目标 Network 事件，那么忽略该事件。
  - `13-5` 如果用户点击“停止监听”、当前 tab 关闭、当前 tab 导航离开 X 或 debugger 被外部 detach，那么跳出循环。
  - `13-6` 否则回到 `13`，继续监听。

- `14` 如果用户点击“停止监听”，那么扩展调用 `chrome.debugger.detach` 解除当前 tab 绑定。
  - `14-1` 如果 detach 成功，那么 popup 显示「未监听」。
  - `14-2` 否则 popup 显示 detach 失败原因，并将状态刷新为 Chrome 实际 debugger 状态。

- `15` 如果当前 tab 关闭，那么扩展清理该 tab 的请求元数据、响应元数据和允许保存图片集合。
  - `15-1` 如果 debugger 仍处于 attach 状态，那么扩展执行 detach。
  - `15-2` 否则只清理内存状态。

# 本地保存条件树

- `16` 如果 Python 本地脚本启动，那么脚本解析自身路径，计算 `captures/` 保存文件夹路径。
  - `16-1` 如果保存文件夹不存在，那么脚本创建保存文件夹。
  - `16-2` 如果保存文件夹已存在，那么脚本复用保存文件夹。

- `17` 如果 Python 本地脚本收到 raw JSON 保存消息，那么脚本按日期追加写入 `captures/raw/YYYY-MM-DD.ndjson`。
  - `17-1` 如果写入成功，那么返回「raw JSON 已保存」。
  - `17-2` 否则写入错误 JSON，返回写入失败原因。

- `18` 如果 Python 本地脚本收到整理后的 tweet JSON 保存消息，那么脚本按 tweet id 写入 `captures/tweets/<tweet_id>.json`。
  - `18-1` 如果同一 tweet id 已存在，那么脚本覆盖或合并同名整理 JSON 文件，输出状态为「tweet JSON 已更新」。
  - `18-2` 否则脚本创建新的 tweet JSON 文件，输出状态为「tweet JSON 已创建」。

- `19` 如果 Python 本地脚本收到图片保存消息，那么脚本根据图片 URL 和关联 tweet id 生成 `captures/images/<tweet_id>/<hash>.<ext>` 并写入图片 bytes。
  - `19-1` 如果图片文件不存在，那么脚本写入图片文件，输出状态为「图片已保存」。
  - `19-2` 如果图片文件已存在，那么脚本跳过写入，输出状态为「图片已存在」。
  - `19-3` 如果图片写入失败，那么脚本写入错误 JSON，返回写入失败原因。

- `20` 如果 Python 本地脚本收到错误记录消息，那么脚本按日期追加写入 `captures/errors/YYYY-MM-DD.ndjson`。
  - `20-1` 如果错误 JSON 写入成功，那么返回「错误已记录」。
  - `20-2` 否则返回写入失败原因给扩展。

# 目录结构条件树

- `21` 如果保存文件夹被创建或复用，那么其下包含 raw JSON、整理 tweet JSON、图片和错误记录目录。
  - `21-1` 如果 raw JSON 需要保存，那么写入 `raw/`。
  - `21-2` 如果整理 tweet JSON 需要保存，那么写入 `tweets/`。
  - `21-3` 如果正文图片需要保存，那么写入 `images/`。
  - `21-4` 如果错误记录需要保存，那么写入 `errors/`。

# 界面与交互条件树

- `22` 如果用户打开 popup，那么 popup 显示当前 tab 状态和计数。
  - `22-1` 如果当前 tab 未监听，那么显示「未监听」和“开始监听”按钮。
  - `22-2` 如果当前 tab 正在监听，那么显示「监听中」、raw JSON 数量、tweet JSON 数量、图片数量、错误数量和“停止监听”按钮。

- `23` 如果扩展保存计数发生变化，那么 popup 更新计数。
  - `23-1` 如果 popup 打开，那么立即刷新显示。
  - `23-2` 否则只更新扩展内部状态。

- `24` 如果出现 attach、detach、body 读取或本地写入错误，那么 popup 显示最新错误摘要。
  - `24-1` 如果错误来自 Chrome debugger API，那么显示 Chrome 返回的错误信息。
  - `24-2` 如果错误来自 Python 本地脚本，那么显示本地脚本返回的错误信息。

# 例外与边界条件树

- `25` 如果目标 JSON 或图片没有自然加载到浏览器，那么工具不得主动请求该资源。
  - `25-1` 如果 tweet JSON 中存在图片 URL 但图片响应未自然加载，那么整理 JSON 只保留 URL。
  - `25-2` 如果图片响应自然加载且 body 可读，那么保存图片文件。

- `26` 如果 response body 因缓存、Chrome 限制、请求生命周期或其他原因不可读取，那么工具记录错误。
  - `26-1` 如果 body 不可读的是 JSON 响应，那么记录 raw JSON 读取失败错误。
  - `26-2` 如果 body 不可读的是图片响应，那么记录图片读取失败错误。

- `27` 如果同一 tweet 或同一图片多次出现，那么工具执行去重。
  - `27-1` 如果 tweet id 已存在，那么更新整理 JSON。
  - `27-2` 如果图片文件已存在，那么跳过图片写入。

- `28` 如果监听期间当前 tab 导航到非 X 页面，那么扩展停止监听。
  - `28-1` 如果 detach 成功，那么 popup 显示「已停止：离开 X 页面」。
  - `28-2` 否则 popup 显示 detach 失败原因。

- `29` 如果 Chrome 显示“扩展正在调试当前 tab”的本地提示，那么工具继续监听。
  - `29-1` 如果用户后续不接受该提示，那么停止监听并转人工确认替代方案。
  - `29-2` 否则继续使用 `chrome.debugger`。

# ERROR 汇总

无。
