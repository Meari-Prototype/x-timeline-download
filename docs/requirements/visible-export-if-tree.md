# X Capture Visible Export Requirements

# 需求总目标
把 `native_host/captures/` 中已经落盘的 X raw JSON、整理后 tweet JSON 和正文图片索引，转换为更接近网页可见内容的离线导出结果。导出结果至少包含作者 id、作者用户名、作者显示名、发帖时间、帖子 id、正文、回复目标、回复时间、互动计数和图片路径，并生成可浏览 HTML、表格 CSV、机器可读 JSONL。

# 事实前提

- 【前提 A1】输入数据来自本项目已经保存的 `native_host/captures/`，脚本不访问网络。
- 【前提 A2】优先从 `captures/raw/*.ndjson` 读取原始 GraphQL/API 响应，以便保留回复关系和互动计数。
- 【前提 A3】当 raw 中无法提供某条 tweet 的完整信息时，脚本从 `captures/tweets/*.json` 读取整理后 tweet JSON 作为回退来源。
- 【前提 A4】图片文件来自 `captures/images/<tweet_id>/`，脚本只引用本地图片路径，不下载图片。
- 【前提 A5】输出目录默认写入 `captures/exports/visible-<timestamp>/`。
- 【前提 A6】输出时区默认使用本机时区；用户传入 `--timezone` 时使用指定 IANA 时区。

# 入口条件树

- `1` 如果用户运行导出脚本，那么脚本读取命令行参数并计算输入目录、输出目录、时区和排序方式。
  - `1-1` 如果用户传入 `--captures`，那么脚本使用该路径作为输入目录。
  - `1-2` 否则脚本使用 `native_host/captures/` 作为输入目录。
- `2` 如果输入目录存在，那么脚本继续扫描数据文件。
  - `2-1` 如果输入目录包含 `raw/` 或 `tweets/`，那么脚本进入数据读取流程。
  - `2-2` 否则脚本退出并显示“未找到 raw/ 或 tweets/ 输入目录”。
- `3` 如果输出目录不存在，那么脚本创建输出目录。
  - `3-1` 如果创建成功，那么脚本继续导出。
  - `3-2` 否则脚本退出并显示写入失败原因。

# 数据流条件树

- `4`【FOREACH raw 文件】如果 `captures/raw/*.ndjson` 存在，那么脚本逐行读取 raw 记录。
  - `4-1` 如果该行可解析为 JSON 且包含 `body`，那么脚本递归扫描 `body` 中的 tweet 对象。
  - `4-2` 否则记录异常到导出报告，跳过该行，继续下一行。
- `5` 如果递归扫描命中对象 `__typename == "Tweet"` 且存在 `rest_id`，那么脚本提取网页可见字段。
  - `5-1` 如果 tweet 包含 `legacy.full_text`，那么写入正文文本。
  - `5-2` 否则正文写为空字符串，并在报告中计入缺正文记录。
  - `5-3` 如果 tweet 包含 `core.user_results.result`，那么提取作者 id、用户名和显示名。
  - `5-4` 否则作者字段写为空值，并在报告中计入缺作者记录。
  - `5-5` 如果 tweet 包含 `legacy.created_at`，那么转换为 ISO 时间和中文显示时间。
  - `5-6` 否则时间字段写为空值，并在报告中计入缺时间记录。
- `6` 如果 tweet 是回复，那么脚本写入回复目标字段。
  - `6-1` 如果存在 `legacy.in_reply_to_status_id_str`，那么写入 `reply_to_tweet_id`。
  - `6-2` 否则 `reply_to_tweet_id` 写为空。
  - `6-3` 如果存在 `legacy.in_reply_to_user_id_str` 或 `legacy.in_reply_to_screen_name`，那么写入对应回复目标作者字段。
  - `6-4` 否则回复目标作者字段写为空。
  - `6-5` 如果该记录是回复且存在发帖时间，那么 `reply_time` 使用该 tweet 的发帖时间。
  - `6-6` 否则 `reply_time` 写为空。
- `7` 如果 tweet 包含互动计数，那么脚本写入计数字段。
  - `7-1` 如果存在 `legacy.reply_count`，那么写入回复数。
  - `7-2` 否则回复数写为空。
  - `7-3` 如果存在 `legacy.retweet_count`、`legacy.favorite_count`、`legacy.quote_count`、`legacy.bookmark_count` 或 `views.count`，那么写入对应字段。
  - `7-4` 否则对应字段写为空。
- `8` 如果 tweet 包含正文图片媒体，那么脚本写入图片字段。
  - `8-1` 如果 `captures/images/<tweet_id>/` 中存在本地图片文件，那么写入本地图片相对路径。
  - `8-2` 否则只写入 raw 中的图片 URL。
- `9` 如果同一 tweet id 多次出现，那么脚本合并记录。
  - `9-1` 如果新记录比旧记录字段更完整，那么用新字段补齐旧记录。
  - `9-2` 否则保留旧记录。

# 主流程条件树

- `10` 如果 raw 扫描完成，那么脚本扫描 `captures/tweets/*.json` 作为回退数据。
  - `10-1` 如果 tweet id 已经存在于导出集合，那么只用整理后 JSON 补齐图片和保存时间字段。
  - `10-2` 否则新增一条来源为 `tweet_json` 的导出记录。
- `11` 如果导出集合非空，那么脚本按时间排序并写入输出文件。
  - `11-1` 如果排序字段存在发帖时间，那么按发帖时间升序或降序排序。
  - `11-2` 否则按 tweet id 排序。
  - `11-3` 写入 `visible_tweets.jsonl`。
  - `11-4` 写入 `visible_tweets.csv`。
  - `11-5` 写入 `visible_tweets.html`。
  - `11-6` 写入 `summary.json`。
- `12` 如果导出集合为空，那么脚本写入空 summary，并显示“没有可导出的 tweet”。

# 界面与交互条件树

- `13` 如果用户打开 `visible_tweets.html`，那么页面显示类似 X 帖子列表的离线视图。
  - `13-1` 如果记录包含作者显示名和用户名，那么显示“显示名 @用户名”。
  - `13-2` 否则显示已有作者 id 或“Unknown author”。
  - `13-3` 如果记录包含正文，那么显示正文并保留换行。
  - `13-4` 否则显示空正文占位。
  - `13-5` 如果记录包含本地图片路径，那么显示缩略图链接。
  - `13-6` 否则不显示图片区域。

# 例外与边界条件树

- `14` 如果 raw 行损坏或字段缺失，那么脚本记录异常并继续处理其他记录。
- `15` 如果旧数据中存在 `rawTypename == "User"` 的污染 JSON，那么脚本跳过该文件并在 summary 中计数。
- `16` 如果文本包含 HTML 特殊字符，那么 HTML 输出必须转义字符。
- `17` 如果 CSV 字段包含换行、逗号或引号，那么 CSV writer 必须正确转义字段。

# ERROR 汇总

无。
