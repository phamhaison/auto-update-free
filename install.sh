#!/bin/bash
# Auto-Update-Free Installer
# Cài đặt ứng dụng lên Linux (Ubuntu/Debian/Fedora/Arch...)

set -e

APP_NAME="Auto-Update-Free"
REPO_URL="https://github.com/phamhaison/auto-update-free.git"
INSTALL_DIR="$HOME/.local/share/$APP_NAME"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor"

echo "=========================================="
echo "  $APP_NAME Installer v1.6.0"
echo "=========================================="
echo ""

# Kiểm tra Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 không tìm thấy. Vui lòng cài đặt Python 3.10+"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Python $PYTHON_VERSION"

# Clone repository
if [ -d "$INSTALL_DIR" ]; then
    echo "📁 Thư mục cài đặt đã tồn tại, cập nhật..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    echo "📥 Clone repository..."
    git clone https://github.com/phamhaison/auto-update-free.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Checkout tag v1.6.0
git checkout v1.6.0 2>/dev/null || git checkout main

# Tạo virtual environment
if [ ! -d "venv" ]; then
    echo "🔧 Tạo virtual environment..."
    python3 -m venv venv
fi

# Cài đặt dependencies
echo "📦 Cài đặt dependencies..."
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt

# Tạo launcher script
echo "🚀 Tạo launcher..."
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/auto-update-free" << 'LAUNCHER_EOF'
#!/bin/bash
# Auto-Update-Free Launcher

SCRIPT_DIR="$HOME/.local/share/Auto-Update-Free"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo "Virtual environment không tìm thấy. Chạy lại installer."
    exit 1
fi

source venv/bin/activate
export QT_QPA_PLATFORMTHEME=gtk3
exec python main.py "$@"
LAUNCHER_EOF

chmod +x "$BIN_DIR/auto-update-free"

# Cài đặt .desktop file
echo "🖥️ Cài đặt menu ứng dụng..."
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/auto-update-free.desktop" << DESKTOP_EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Auto-Update-Free
Comment=Tự động quét và cập nhật mô hình AI miễn phí từ 9router/OmniRouter vào OpenCode
Exec=$BIN_DIR/auto-update-free
Icon=auto-update-free
Terminal=false
Categories=Development;Utility;Network;
StartupNotify=true
StartupWMClass=Auto-update-free
TryExec=$BIN_DIR/auto-update-free
DESKTOP_EOF

# Cài đặt icon
echo "🎨 Cài đặt icon..."
mkdir -p "$ICON_DIR/16x16/apps"
mkdir -p "$ICON_DIR/32x32/apps"
mkdir -p "$ICON_DIR/48x48/apps"
mkdir -p "$ICON_DIR/64x64/apps"
mkdir -p "$ICON_DIR/128x128/apps"
mkdir -p "$ICON_DIR/256x256/apps"
mkdir -p "$ICON_DIR/512x512/apps"

cd "$INSTALL_DIR"
if [ -f "icon.png" ]; then
    for size in 16 32 48 64 128 256 512; do
        convert icon.png -resize ${size}x${size} "$ICON_DIR/${size}x${size}/apps/auto-update-free.png" 2>/dev/null || \
        cp icon.png "$ICON_DIR/${size}x${size}/apps/auto-update-free.png"
    done
    # Icon mặc định
    cp icon.png "$HOME/.local/share/icons/auto-update-free.png" 2>/dev/null || true
fi

# Cập nhật desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

if command -v gtk-update-icon-cache &> /dev/null; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo ""
echo "=========================================="
echo "  ✅ Cài đặt hoàn tất!"
echo "=========================================="
echo ""
echo "Bạn có thể chạy ứng dụng bằng:"
echo "  - Menu ứng dụng: Auto-Update-Free"
echo "  - Terminal: auto-update-free"
echo ""
echo "Thư mục cài đặt: $INSTALL_DIR"
echo "Launcher: $BIN_DIR/auto-update-free"
echo ""
echo "Lần đầu chạy sẽ tạo config tại ~/.config/auto-update-free/config.json"
echo "Cấu hình 9router/OmniRouter qua giao diện ⚙️ Cài đặt"
echo ""
LAUNCHER_EOF
chmod +x install.sh