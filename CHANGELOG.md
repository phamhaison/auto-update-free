# Changelog - Auto-Update-Free

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.0] - 2026-10-21

### Fixed - Critical
- **OpenCode Desktop v1.19.3 không nhận provider/model mới** - Root cause: thiếu `auth.json`, chỉ ghi `opencode.jsonc`, provider ID trùng lặp, whitelist chặn model mới
- **Lỗi cỡ chữ HiDPI X11** - Tên model bị phóng to gấp đôi, cắt cụt trên màn hình 4K/scale > 100%
- **Bug match URL** - `'host:20128'` substring match sai vào `'localhost:20128'` → 9router và OmniRouter gộp nhầm provider ID

### Added - Major Features
- **Đồng bộ đa tầng OpenCode** (`OpenCodeConfigManager.sync_all_opencode`)
  - Ghi đồng thời `opencode.json`, `opencode.jsonc`, `config.json`
  - Tự động backup timestamp trước mỗi lần ghi (atomic write via `.tmp` + `os.replace`)
- **Đăng ký xác thực tự động** (`sync_auth_json`)
  - Ghi API key 9router & OmniRouter vào `~/.local/share/opencode/auth.json`
  - OpenCode Desktop v1.19.3 hiển thị cả 2 router ở "Nhà cung cấp được kết nối"
- **Nhận diện Provider ID thông minh** (`_find_matching_provider_keys`)
  - Match theo ID, tên hiển thị, `baseURL`/endpoint (`:20128`), host:port exact matching
  - Tự động xóa `whitelist`/`blacklist`/`disabled_providers` chặn model mới
- **Schema model chuẩn OpenCode Desktop v1.19+**
  - Mỗi model: `id`, `name`, `tool_call: true`, `temperature: true`
  - Provider: `api` + `options.baseURL` + `options.apiKey` + `npm: @ai-sdk/openai-compatible`
- **Lexer JSONC State-Machine an toàn tuyệt đối** (`strip_jsonc_comments`)
  - Không bao giờ cắt nhầm `//` hoặc `/* */` bên trong chuỗi JSON `"..."`
  - Hỗ trợ escape sequence `\"`, `\\` trong chuỗi
- **Hệ thống hộp thoại phẳng hiện đại** (thay thế `tkinter.messagebox`)
  - `ConfirmUpdateDialog` (720×580): 2 thẻ thống kê 9router/OmniRouter, tùy chọn "Làm mới model cũ", xem trước danh sách 162 mục
  - `UpdateSuccessDialog` (680×500): Chi tiết file ghi, auth files, hướng dẫn 3 bước kiểm tra OpenCode
  - `ModernAlertDialog` (540×290): Info/Warning/Error style thống nhất
- **Sửa lỗi HiDPI X11** - Font pixel âm (`-12`, `-10`) cho `tk.Label` trong Native Flat Row
- **Native Flat Row Rendering** (`_create_fast_native_row`)
  - `tk.Frame` + `tk.Checkbutton` + `tk.Label` phẳng (0 Canvas/PIL overhead)
  - Vẽ 100+ dòng < 0.05s (vs 143s v1.4.0 trên X11 phần mềm)
- **UI Event Batching 150ms** (`_start_ui_flush_timer`, `flush_ui_queues`)
  - Gom log/status/progress/free rows vào buffer, flush 1 lần/150ms
  - Triệt tiêu after-queue backlog (kết quả đầu tiên Pha 2 xuất hiện 2-3s vs 7 phút)
- **Lazy Tab Rendering** - Tab 2 ("Toàn bộ Models") chỉ render khi người dùng click vào
- **Priority Queue 2 tầng + Smart Circuit Breaker**
  - Tier 1: 9router, explicit free, combo members, Core Free Providers (22 prefix) → chạy trước
  - Tier 2: Catalog mở rộng (github/, nvidia/, mistral/...) có Circuit Breaker
  - Circuit Breaker: ≥2 lỗi `NO_ACCOUNT/503` hoặc ≥4 lỗi liên tiếp → ngắt nhanh provider đó
  - 32 workers, timeout 10s, max_tokens=6, chỉ retry 429 (1 lần, nghỉ 0.8s)
- **59 Combos chuẩn xác** (30 9router + 29 OmniRouter)
  - Ưu tiên `/v1/combos` trước `/api/combos` (tránh 401/403)
  - Mặc định `include_auto_combos=False` loại 38 mẫu `auto/*` ảo của OmniRouter

### Changed
- **APP_VERSION** → `1.6.0`
- **Window size** 1280×840 (min 1060×680), Settings 820×740 (min 720×580) resizable, no grab
- **Control bar** gọn gàng, nút "Chọn hết/Bỏ chọn" không tràn mép
- **Tab 1 header** tách hàng tiêu đề & hàng lọc/nút bấm → không cắt chữ
- **Tab 2** font `DejaVu Sans Mono -12` / `DejaVu Sans -10` pixel cố định
- **Settings** thêm checkbox "Bao gồm mẫu auto/*", hiển thị file auth.json sẽ đồng bộ
- **Deep scan** mặc định bật, checkbox trên thanh điều khiển

### Performance
| Metric | v1.4.0 | v1.5.0 | v1.6.0 |
|--------|--------|--------|--------|
| Phase 1 UI render | 143s | <1s | **<0.05s** |
| Phase 2 first result | ~7 min | 2-3s | **2-3s** |
| Phase 2 total | 776s | 87s | **20-35s** |
| Combos count | 97 (sai) | 59 | **59** |
| Free models working | 108 | 103 | **~105** |

---

## [1.5.0] - 2026-10-20

### Added
- **Native Flat Row** (tk native widgets) - vẽ 100+ dòng < 0.05s
- **UI Event Batching 150ms** - gom cập nhật UI, triệt tiêu nghẽn after-queue
- **Priority Queue 2 tầng** - Tier 1 (core free) chạy trước, Tier 2 có Circuit Breaker
- **Smart Provider Circuit Breaker** - ngắt nhanh provider 503/401/403 liên tiếp
- **32 Workers song song** - timeout 10s, max_tokens=6, retry chỉ 429
- **59 Combos chuẩn xác** - ưu tiên `/v1/combos`, loại `auto/*` mặc định
- **Settings Dialog** 820×720, resizable, no grab, bottom bar cố định 64px
- **Single-instance IPC** port 20129 - lan 2 thoát 0.38s, 1 cửa sổ
- **Window 1280×840**, min 1060×680, centered
- **Pagination 60/trang** Tab 2 + "Tải thêm"
- **Segmented filter** 9router/OmniRouter cho cả Combos & Free Models

### Fixed
- Config auto-upgrade key OmniRouter mới + `deep_scan_providers` + `opencode_path`
- `sanitize_endpoint` chuẩn hóa 6 case endpoint
- Merge OpenCode bảo toàn `$schema`, `mcp`, provider khác, backup atomic

---

## [1.4.0] - 2026-10-19

### Added
- Two-phase parallel scan (Phase 1: combos tức thì, Phase 2: verify free models)
- 16 workers Phase 2, deep scan providers (ag, oc, kc, gemini, ollama...)
- Tab layout: Combos (trái) + Free Models hoạt động (phải) + Toàn bộ Models + Logs
- Segmented filter router cho Tab 1
- OpenCode merge an toàn (backup, atomic write, giữ provider khác)
- Config auto-sanitize endpoint (`/v1api` → `/v1`)

---

## [1.3.0] - 2026-10-18

### Added
- Pagination 60/trang + "Tải thêm" Tab 2
- Virtual filtering trong RAM (6000 models ~87ms)
- Single-instance IPC port 20129
- ThreadPoolExecutor 6 workers standalone test

---

## [1.2.0] - 2026-10-17

### Added
- Initial GUI với CustomTkinter
- Combo/Free classification (regex, metadata, provider prefix)
- OpenCode config merge (backup, atomic write)
- Desktop launcher + icon

---

## [1.1.0] - 2026-10-16

### Added
- Core logic: APIClient, ModelAnalyzer, ConfigManager
- Fetch models + combos từ 9router & OmniRouter
- Free model verification (ping test)

---

## [1.0.0] - 2026-10-15

### Added
- Project structure, requirements, basic CLI
