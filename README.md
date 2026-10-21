# Auto-Update-Free

**Tự động quét và đồng bộ Combos & Mô hình AI Miễn phí từ 9router / OmniRouter vào OpenCode**

Một ứng dụng desktop Linux (CustomTkinter) giúp bạn quét toàn bộ các mô hình AI miễn phí từ 9router và OmniRouter, sau đó đồng bộ an toàn vào cấu hình OpenCode (`opencode.json`, `opencode.jsonc` và `auth.json`).

## ✨ Tính năng chính

- 🔍 **Quét toàn diện 2 router song song**: 9router (Local) và OmniRouter (NAS)
- 📦 **Phân loại thông minh**: Tự động nhận diện Combos (100%) và Free Models (có `:free`, metadata free, Core Free Providers)
- ⚡ **Kiểm tra thực tế (Ping test)**: 32 luồng song song, Fast-Fail, Circuit Breaker tự động bỏ qua provider không có account
- 🔐 **Đồng bộ đa tầng an toàn**: Ghi đồng thời vào `opencode.json`, `opencode.jsonc` và `~/.local/share/opencode/auth.json`
- 🛡️ **Bảo toàn cấu hình**: Backup tự động, atomic write, giữ nguyên các provider khác, MCP, schema
- 🎨 **Giao diện hiện đại**: Native Flat Row (tkinter native, 0 Canvas overhead), UI Event Batching 150ms, Lazy Render Tab 2
- 🖥️ **Tích hợp Linux**: Single-instance IPC, .desktop entry, WM_CLASS đúng, HiDPI fix (font pixel âm)
- 🌐 **Hỗ trợ HiDPI**: Font pixel âm (-12/-10) hiển thị tên model dài không bị cắt

## 📸 Giao diện

- **Tab 1**: Danh sách Combos (cột trái) + Free Models đang hoạt động (cột phải) - có bộ lọc theo router
- **Tab 2**: Toàn bộ Models & Router - tìm kiếm, lọc, phân trang 60 mục/trang
- **Tab 3**: Nhật ký tiến trình chi tiết

## 🚀 Cài đặt nhanh

### Yêu cầu
- Linux (Ubuntu 22.04+, Debian 12+, Fedora 38+, Arch, v.v.)
- Python 3.10+
- Git

### Cài đặt từ source
```bash
git clone https://github.com/<your-username>/auto-update-free.git
cd auto-update-free
chmod +x install.sh
./install.sh
```

Script `install.sh` sẽ:
1. Tạo virtual environment (`venv/`)
2. Cài đặt dependencies (`requests`, `customtkinter`, `pillow`)
3. Tạo launcher `~/.local/bin/auto-update-free`
4. Cài đặt file `.desktop` vào `~/.local/share/applications/`
5. Cài đặt icon vào `~/.local/share/icons/hicolor/`

Sau khi cài đặt, bạn có thể chạy từ menu ứng dụng hoặc terminal:
```bash
auto-update-free
```

## ⚙️ Cấu hình

Lần đầu chạy, ứng dụng sẽ tạo file cấu hình tại `~/.config/auto-update-free/config.json` với mặc định:

```json
{
  "9router": {
    "name": "9router (Local)",
    "endpoint": "http://localhost:20128/v1",
    "api_key": "sk-921042c36766f489-qjn67j-65503176"
  },
  "omnirouter": {
    "name": "OmniRouter (NAS)",
    "endpoint": "http://son-server.tail8cd54f.ts.net:20128/v1",
    "api_key": "sk-c8231f142e2df954-7a548c-a6588128"
  },
  "opencode_path": "",
  "deep_scan_providers": true,
  "include_auto_combos": false,
  "replace_router_models": true
}
```

Bạn có thể thay đổi endpoint/API key qua giao diện **⚙️ Cài đặt Router & OpenCode**.

## 🔄 Quy trình sử dụng

1. **Quét & Kiểm tra**: Bấm nút 🔍 *Quét & Kiểm tra* - ứng dụng sẽ:
   - Pha 1: Kết nối 2 router, lấy Combos (tức thì) và danh sách ứng viên Free
   - Pha 2: Kiểm tra thực tế các ứng viên Free (32 luồng, ưu tiên Tier 1, Circuit Breaker)
2. **Chọn mô hình**: Tích chọn Combos/Free Models muốn đồng bộ (mặc định chọn tất cả)
3. **Cập nhật vào OpenCode**: Bấm 📥 *Cập nhật vào OpenCode* - hộp thoại xác nhận hiện đại hiển thị preview đầy đủ
4. **Khởi động lại OpenCode Desktop**: Để thấy các model mới trong mục "Nhà cung cấp" và "Mô hình"

## 🏗️ Kiến trúc kỹ thuật

- **Native Flat Row**: `tk.Frame` + `tk.Checkbutton` + `tk.Label` (font pixel âm -12/-10) - vẽ 100+ dòng < 0.05s
- **UI Event Batching**: Gom log/status/progress/free rows, flush 1 lần/150ms
- **Priority Queue 2 tầng**: Tier 1 (Core Free Providers, explicit free, combo members) chạy trước
- **Smart Circuit Breaker**: Tự động ngắt provider trả `503/401/403` liên tiếp (≥2 NO_ACCOUNT hoặc ≥4 lỗi)
- **JSONC Lexer an toàn**: State-machine parser, không bao giờ làm hỏng chuỗi chứa `//` hoặc `/*`
- **Multi-file sync**: Đồng bộ đồng thời `opencode.json`, `opencode.jsonc`, `config.json`, `auth.json`
- **Single-instance IPC**: Port 20129, lần 2 kích hoạt cửa sổ cũ thoát 0.2s

## 📦 Build & Release

```bash
# Tạo package wheel
python -m build

# Tạo executable (nếu cần)
# pyinstaller --onefile --windowed --icon=icon.ico --name auto-update-free main.py
```

## 📄 Giấy phép

MIT License - xem file [LICENSE](LICENSE)

## 🤝 Đóng góp

1. Fork repository
2. Tạo branch feature (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Mở Pull Request

## 🐛 Báo lỗi

Tạo issue tại [GitHub Issues](https://github.com/<your-username>/auto-update-free/issues) với:
- Mô tả lỗi chi tiết
- Log từ Tab "Nhật ký tiến trình"
- Môi trường (OS, Python version, customtkinter version)

## 🙏 Credits

- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) - Modern UI toolkit
- [Requests](https://github.com/psf/requests) - HTTP library
- [Pillow](https://github.com/python-pillow/Pillow) - Image processing
- OpenCode - AI coding agent

---

**Phiên bản**: 1.6.0  
**Tác giả**: Auto-Update-Free Team