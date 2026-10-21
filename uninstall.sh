#!/bin/bash
# Auto-Update-Free Uninstaller
# Gỡ cài đặt hoàn toàn ứng dụng khỏi Linux

set -e

APP_NAME="Auto-Update-Free"
INSTALL_DIR="$HOME/.local/share/$APP_NAME"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor"
CONFIG_DIR="$HOME/.config/$APP_NAME"

echo "=========================================="
echo "  $APP_NAME Uninstaller v1.6.0"
echo "=========================================="
echo ""

# Xóa launcher
if [ -f "$BIN_DIR/auto-update-free" ]; then
    echo "🗑️ Xóa launcher..."
    rm -f "$BIN_DIR/auto-update-free"
fi

# Xóa desktop entry
if [ -f "$DESKTOP_DIR/auto-update-free.desktop" ]; then
    echo "🗑️ Xóa menu ứng dụng..."
    rm -f "$DESKTOP_DIR/auto-update-free.desktop"
fi

# Xóa icon
echo "🗑️ Xóa icon..."
for size in 16 32 48 64 128 256 512; do
    rm -f "$ICON_DIR/${size}x${size}/apps/auto-update-free.png"
done
rm -f "$HOME/.local/share/icons/auto-update-free.png"

# Xóa thư mục cài đặt
if [ -d "$INSTALL_DIR" ]; then
    echo "🗑️ Xóa thư mục cài đặt: $INSTALL_DIR"
    rm -rf "$INSTALL_DIR"
fi

# Xóa config (tuỳ chọn - hỏi người dùng)
echo ""
read -p "❓ Bạn có muốn xóa cả cấu hình người dùng (~/.config/auto-update-free)? [y/N]: " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [ -d "$CONFIG_DIR" ]; then
        echo "🗑️ Xóa cấu hình: $CONFIG_DIR"
        rm -rf "$CONFIG_DIR"
    fi
else
    echo "📁 Giữ lại cấu hình tại: $CONFIG_DIR"
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
echo "  ✅ Gỡ cài đặt hoàn tất!"
echo "=========================================="
echo ""
echo "Ứng dụng đã được gỡ bỏ hoàn toàn khỏi hệ thống."
if [ -d "$CONFIG_DIR" ]; then
    echo "Cấu hình người dùng vẫn được giữ tại: $CONFIG_DIR"
fi
echo ""
