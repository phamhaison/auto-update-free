# Auto-Update-Free v1.6.0

> **Đồng bộ Combos & Mô hình AI Miễn phí từ 9router + OmniRouter vào OpenCode**  
> Khắc phục triệt để lỗi OpenCode Desktop không nhận provider/model mới, giao diện hiện đại, hiệu suất cực đại.

## ✨ Tính năng chính (v1.6.0)

| Tính năng | Mô tả |
|-----------|-------|
| **Đồng bộ đa tầng OpenCode** | Ghi đồng thời `opencode.json`, `opencode.jsonc`, `config.json` + `~/.local/share/opencode/auth.json` |
| **OpenCode Desktop nhận provider ngay** | Tự động đăng ký API key 9router & OmniRouter vào `auth.json` → hiện trong "Nhà cung cấp được kết nối" |
| **Nhận diện Provider ID thông minh** | Tìm provider theo ID/tên/endpoint, xóa `whitelist`/`blacklist` cũ, không tạo bản sao rời rạc |
| **Lexer JSONC an toàn** | State-machine parser, không bao giờ hỏng chuỗi chứa `//` hoặc `/*` |
| **Hộp thoại phẳng hiện đại** | `ConfirmUpdateDialog`, `UpdateSuccessDialog`, `ModernAlertDialog` thay thế `messagebox` cổ điển |
| **Sửa lỗi HiDPI X11** | Font pixel âm (-12/-10) → tên model dài hiển thị đầy đủ, không bị phóng to/cắt cụt |
| **32 Workers + Priority Queue + Circuit Breaker** | Pha 2: 20-35s (vs 776s v1.4.0), kết quả đầu tiên 2-3s |
| **59 Combos chuẩn xác** | 30 (9router) + 29 (OmniRouter), loại 38 mẫu `auto/*` ảo |

---

## 🚀 Cài đặt nhanh

### Yêu cầu
- **Ubuntu 22.04+ / Debian 12+ / Linux Mint 21+** (GNOME/KDE/XFCE)
- **Python 3.10+** (đã có sẵn trên Ubuntu 22.04+)
- **9router** chạy local tại `http://localhost:20128/v1`
- **OmniRouter** truy cập qua Tailscale/VPN tại `http://son-server.tail8cd54f.ts.net:20128/v1`

### Cách 1: Script tự động (Khuyên dùng)

```bash
# Clone repo (private - cần token hoặc SSH key)
git clone https://github.com/phamhaison/auto-update-free.git
cd auto-update-free

# Chạy script cài đặt (tự tạo venv, cài deps, tạo desktop shortcut)
chmod +x install.sh
./install.sh
```

### Cách 2: Thủ công

```bash
git clone https://github.com/phamhaison/auto-update-free.git
cd auto-update-free

# Tạo môi trường ảo
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Chạy ứng dụng
./run.sh
```

### Cách 3: Chạy từ source (dev)

```bash
cd auto-update-free
source venv/bin/activate
python main.py
```

---

## ⚙️ Cấu hình

### 1. Khởi động ứng dụng
- Mở từ **Menu ứng dụng** → **Auto-Update-Free**
- Hoặc chạy `./run.sh` từ terminal

### 2. Cài đặt Router & OpenCode
Nhấn **⚙ Cài đặt Router & OpenCode** trên thanh tiêu đề:

| Tab | Cài đặt |
|-----|---------|
| **9router (Local)** | Endpoint: `http://localhost:20128/v1`<br>API Key: `sk-921042c36766f489-qjn67j-65503176` |
| **OmniRouter (NAS)** | Endpoint: `http://son-server.tail8cd54f.ts.net:20128/v1`<br>API Key: `sk-c8231f142e2df954-7a548c-a6588128` |
| **OpenCode** | Đường dẫn file cấu hình (tự nhận diện `~/.config/opencode/opencode.jsonc`)<br>☑ **Bao gồm mẫu `auto/*`** (tùy chọn) |

Nhấn **Kiểm tra kết nối** để verify, sau đó **Lưu toàn bộ cấu hình**.

### 3. Quét & Đồng bộ

1. Nhấn **Quét & Kiểm tra** → Chờ Pha 1 (Combos) + Pha 2 (Free Models hoạt động)
2. Kết quả hiển thị 2 cột:
   - **Trái**: Danh sách 59 Combos (có checkbox, lọc 9router/OmniRouter)
   - **Phải**: Free Models đang hoạt động (có độ trễ ms)
2. Tick chọn mục cần đồng bộ (mặc định: tất cả)
3. Nhấn **Cập nhật vào OpenCode**
4. Xác nhận trong hộp thoại `ConfirmUpdateDialog` (có xem trước 162 mục)
5. Hộp thoại `UpdateSuccessDialog` báo thành công + hướng dẫn 3 bước kiểm tra OpenCode

---

## 🔧 Kiểm tra sau khi đồng bộ

```bash
# 1. Khởi động lại OpenCode Desktop (thoát hẳn incluyendo System Tray)
# 2. Mở OpenCode Desktop → Settings → Providers
#    ✅ 9router (Local) - Đã kết nối
#    ✅ OmniRouter (NAS) - Đã kết nối
# 3. Mở Models → Bật hiển thị Combos/Free Models mới
# 4. Hoặc gõ `/models` trong chat để chọn ngay
```

**File cấu hình được ghi:**
- `~/.config/opencode/opencode.json` (chuẩn OpenCode Desktop)
- `~/.config/opencode/opencode.jsonc` (nếu có)
- `~/.config/opencode/config.json` (nếu có)
- `~/.local/share/opencode/auth.json` (API key xác thực)

**Backup tự động:** `opencode.json.bak_YYYYMMDD_HHMMSS` trước mỗi lần ghi.

---

## 🛠️ Gỡ cài đặt

```bash
cd auto-update-free
./uninstall.sh
# Hoặc thủ công:
rm -rf ~/.config/auto-update-free
rm -f ~/.local/share/applications/auto-update-free.desktop
rm -f ~/.local/bin/auto-update-free
rm -rf /home/haison/Các dự án/Auto-Update-Free  # thư mục source
```

---

## 📁 Cấu trúc dự án

```
auto-update-free/
├── main.py                 # Entry point (1818 dòng, v1.6.0)
├── run.sh                  # Launcher script (tự active venv)
├── install.sh              # Cài đặt tự động + desktop shortcut
├── uninstall.sh            # Gỡ cài đặt sạch
├── requirements.txt        # customtkinter>=5.2.0, requests>=2.31.0
├── icon.png / icon.ico     # Icon ứng dụng
├── create_icon.py          # Tạo icon từ code
├── venv/                   # Python virtual environment (tự tạo)
├── README.md               # File này
├── LICENSE                 # MIT License
├── .gitignore
└── CHANGELOG.md            # Lịch sử phiên bản
```

---

## 📋 Changelog

### v1.6.0 (2026-10-21)
- **Fix critical**: OpenCode Desktop v1.19.3 không nhận provider/model mới
- **New**: Đồng bộ đa tầng (opencode.json + opencode.jsonc + auth.json)
- **New**: Hộp thoại phẳng hiện đại (Confirm/Success/Alert)
- **Fix**: Lỗi cỡ chữ HiDPI X11 (font pixel âm -12/-10)
- **Fix**: Bug match URL (`host:20128` → exact `host:port`)
- **Perf**: Native Flat Row (<0.05s), UI Batching 150ms, 32 workers
- **Arch**: Priority Queue 2 tầng + Smart Circuit Breaker

### v1.5.0 (2026-10-20)
- Native Flat Row rendering, UI Event Batching 150ms
- Priority Queue + Circuit Breaker
- 59 Combos chuẩn xác (loại `auto/*`)
- Settings 820x720 resizable, IPC single-instance

### v1.4.0 (2026-10-19)
- Two-phase parallel scan (Phase 1: combos, Phase 2: free models)
- 16 workers, deep scan providers
- Window 1280x840, modern UI

### v1.3.0 (2026-10-18)
- Pagination 60/trang, virtual filtering
- Single-instance IPC port 20129

### v1.2.0 (2026-10-17)
- Initial GUI với CustomTkinter
- Combo/Free classification, OpenCode merge

---

## 🐛 Troubleshooting

| Vấn đề | Giải pháp |
|--------|-----------|
| **ModuleNotFoundError: customtkinter** | `source venv/bin/activate && pip install -r requirements.txt` |
| **OpenCode Desktop không thấy OmniRouter** | Kiểm tra `~/.local/share/opencode/auth.json` có key `omnirouter`; restart OpenCode Desktop hẳn |
| **Endpoint 401/403** | Kiểm tra API key trong Settings; 9router key local, OmniRouter key NAS |
| **Giao diện treo khi quét** | v1.6.0 đã fix bằng Native Flat Row + Batching 150ms; nếu vẫn treo → giảm `deep_scan_providers` |
| **Tên model bị cắt/cỡ to** | v1.6.0 fix font pixel âm; nếu vẫn lỗi → kiểm tra DPI scaling GNOME (`gsettings get org.gnome.desktop.interface scaling-factor`) |

---

## 📄 License

MIT License - Xem file [LICENSE](LICENSE)

---

## 🤝 Đóng góp

1. Fork repo
2. Tạo branch feature (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push branch (`git push origin feature/amazing-feature`)
5. Tạo Pull Request

---

## 📞 Hỗ trợ

- **Issues**: [GitHub Issues](https://github.com/phamhaison/auto-update-free/issues)
- **Email**: phamhaison@example.com

---

*Auto-Update-Free v1.6.0 — Làm cho AI miễn phí dễ dàng như chưa từng có.*
