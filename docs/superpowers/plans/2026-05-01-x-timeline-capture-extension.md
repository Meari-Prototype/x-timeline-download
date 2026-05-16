# X Timeline Capture Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Chrome-only extension that uses `chrome.debugger` to read current-tab X Network responses and a Python Native Messaging host to save raw JSON, normalized tweet JSON, and naturally loaded tweet body images under `captures/`.

**Architecture:** The extension owns tab attachment, CDP Network event handling, filtering, tweet extraction, image allowlisting, counters, and popup state. The Python host owns local persistence and never sends network requests. Shared parsing/filtering logic is kept in small ESM modules with Node tests.

**Tech Stack:** Chrome Manifest V3, JavaScript ESM, Chrome Debugger API, Chrome Native Messaging, Python 3 standard library, Node built-in test runner, Python unittest.

---

### Task 1: Core Filters And Tweet Parser

**Files:**
- Create: `extension/lib/filters.mjs`
- Create: `extension/lib/tweet_parser.mjs`
- Create: `tests/js/filters.test.mjs`
- Create: `tests/js/tweet_parser.test.mjs`

- [ ] Write tests for X page detection, JSON/image/video classification, pbs media identity normalization, tweet extraction, and quote tweet image inclusion.
- [ ] Run `node --test tests/js/*.test.mjs` and confirm the tests fail because modules are missing.
- [ ] Implement the smallest filter and parser modules that satisfy the tests.
- [ ] Run `node --test tests/js/*.test.mjs` and confirm all JavaScript unit tests pass.

### Task 2: Python Native Host Persistence

**Files:**
- Create: `native_host/x_capture_host.py`
- Create: `native_host/x_capture_host.bat`
- Create: `native_host/install_host.ps1`
- Create: `tests/python/test_host_storage.py`

- [ ] Write Python tests for host message framing, folder creation, raw JSON append, tweet JSON writing, image writing, duplicate image skipping, and error append.
- [ ] Run `python -m unittest discover -s tests/python -v` and confirm the tests fail because the host module is missing.
- [ ] Implement the Python host with stdio Native Messaging framing and storage helpers.
- [ ] Run `python -m unittest discover -s tests/python -v` and confirm all Python unit tests pass.

### Task 3: Chrome Extension Shell And CDP Capture

**Files:**
- Create: `extension/manifest.json`
- Create: `extension/background.mjs`
- Create: `extension/popup.html`
- Create: `extension/popup.mjs`
- Create: `extension/styles.css`
- Create: `tests/js/background_core.test.mjs`
- Create: `extension/lib/background_core.mjs`

- [ ] Write tests for background session bookkeeping using a fake Chrome adapter: start only X tabs, stop session, update counters, allowlist image identities after tweet JSON, and reject video responses.
- [ ] Run `node --test tests/js/*.test.mjs` and confirm the new tests fail because `background_core.mjs` is missing.
- [ ] Implement background core as dependency-injected logic, then wire it to real `chrome.debugger`, `chrome.runtime`, and popup messages in `background.mjs`.
- [ ] Implement popup controls for status, counters, last error, start, and stop.
- [ ] Run `node --test tests/js/*.test.mjs` and confirm all JavaScript unit tests pass.

### Task 4: Manual Install Documentation And Final Verification

**Files:**
- Create: `README.md`
- Modify: `docs/requirements/x-capture-if-tree.md`

- [ ] Document manual Chrome unpacked extension loading and Native Messaging Host registration with `native_host/install_host.ps1 -ExtensionId <id>`.
- [ ] Document output layout under `native_host/captures/`.
- [ ] Run JavaScript tests: `node --test tests/js/*.test.mjs`.
- [ ] Run Python tests: `python -m unittest discover -s tests/python -v`.
- [ ] Validate JSON files parse with `python -m json.tool extension/manifest.json`.
