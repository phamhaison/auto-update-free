#!/bin/bash
# Cài đặt Icon và Desktop Entry cho Auto-Update-Free
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ICON_SRC="$SCRIPT_DIR/icon.png"
DESKTOP_SRC="$SCRIPT_DIR/auto-update-free.desktop"

echo "🔧 Bắt đầu cấu hình Icon và Launcher cho Auto-Update-Free..."

mkdir -p "$HOME/.local/share/icons/hicolor/256x256/apps"
mkdir -p "$HOME/.local/share/icons"
mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/bin"

if [ -f "$ICON_SRC" ]; then
    cp -f --remove-destination "$ICON_SRC" "$HOME/.local/share/icons/auto-update-free.png"
    cp -f --remove-destination "$ICON_SRC" "$HOME/.local/share/icons/hicolor/256x256/apps/auto-update-free.png"
    echo "✅ Đã cài đặt icon vào ~/.local/share/icons/auto-update-free.png"
else
    echo "⚠️ Không tìm thấy icon.png tại $ICON_SRC, vui lòng chạy create_icon.py trước!"
fi

rm -f "$HOME/bin/auto-update-free"
cat > "$HOME/bin/auto-update-free" << RUNNER
#!/bin/bash
exec "$SCRIPT_DIR/run.sh" "\$@"
RUNNER
chmod +x "$HOME/bin/auto-update-free"

cp -f --remove-destination "$DESKTOP_SRC" "$HOME/.local/share/applications/auto-update-free.desktop"
chmod +x "$HOME/.local/share/applications/auto-update-free.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications"
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" -f -t 2>/dev/null || true
fi

echo "🎉 Hoàn tất! Ứng dụng đã xuất hiện trong App Menu và hiển thị icon chuẩn trên Dock."
