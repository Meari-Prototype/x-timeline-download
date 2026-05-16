# X Timeline Local Capture

## 中文

这是一个本地 Chrome 拓展，用来在浏览 X 时间线时保存当前页面已经自然加载的 X Network JSON，并在本地生成可读的推文导出文件。

它不重放请求，不注入页面脚本，不修改 cookie，不使用代理，也不做 HTTPS MITM。

### 怎么用

1. 打开 Chrome 的 `chrome://extensions`。
2. 开启 Developer mode。
3. 点击 Load unpacked，选择本项目的 `extension/` 目录。
4. 复制 Chrome 显示的 extension ID。
5. 在项目根目录运行：

```powershell
.\native_host\install_host.ps1 -ExtensionId <chrome_extension_id>
```

6. 打开 `https://x.com/home` 或其他 X 页面。
7. 点击拓展图标，再点击“开始监听”。
8. 正常浏览 X 页面。
9. 结束后点击“停止监听”。
10. 在拓展弹窗的抓取记录里点击“打开目录”，查看本地导出文件。

导出文件会写入：

```text
native_host/captures/sessions/<session_id>/
```

常用文件包括：

```text
visible_tweets.html
visible_tweets.csv
visible_tweets.jsonl
visible_tweets_pure.txt
summary.json
```

## English

This is a local Chrome extension for saving X timeline data while you browse. It reads the current tab's already-loaded X Network JSON and writes local, readable tweet export files.

It does not replay requests, inject page scripts, modify cookies, use a proxy, or perform HTTPS MITM.

### How to Use

1. Open `chrome://extensions` in Chrome.
2. Enable Developer mode.
3. Click Load unpacked and select this project's `extension/` directory.
4. Copy the extension ID shown by Chrome.
5. Run this command from the project root:

```powershell
.\native_host\install_host.ps1 -ExtensionId <chrome_extension_id>
```

6. Open `https://x.com/home` or another X page.
7. Click the extension icon, then click “开始监听”.
8. Browse X normally.
9. Click “停止监听” when finished.
10. In the extension popup, click “打开目录” on a capture record to view the local export files.

Exports are written under:

```text
native_host/captures/sessions/<session_id>/
```

Common files:

```text
visible_tweets.html
visible_tweets.csv
visible_tweets.jsonl
visible_tweets_pure.txt
summary.json
```
