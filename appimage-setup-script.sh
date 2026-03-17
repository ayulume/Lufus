#!/bin/bash
set -e

# ---------- Custom tree printer (no external dependencies) ----------
print_tree() {
    local dir="$1"
    local maxdepth="${2:-3}"
    _print_tree_recursive "$dir" "" 0 "$maxdepth"
}

_print_tree_recursive() {
    local current_dir="$1"
    local prefix="$2"
    local depth="$3"
    local maxdepth="$4"

    if [ $depth -ge $maxdepth ]; then
        echo "${prefix}└── ... (max depth reached)"
        return
    fi

    local items=()
    while IFS= read -r -d '' item; do
        items+=("$item")
    done < <(find "$current_dir" -mindepth 1 -maxdepth 1 -print0 2>/dev/null | sort -z)

    local count=${#items[@]}
    local i=0

    for item in "${items[@]}"; do
        i=$((i+1))
        local basename_item
        basename_item=$(basename "$item")
        if [ $i -eq $count ]; then
            echo "${prefix}└── $basename_item"
            local new_prefix="${prefix}    "
        else
            echo "${prefix}├── $basename_item"
            local new_prefix="${prefix}│   "
        fi

        if [ -d "$item" ]; then
            _print_tree_recursive "$item" "$new_prefix" $((depth+1)) "$maxdepth"
        fi
    done
}
# --------------------------------------------------------------------

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Project root: $PROJECT_ROOT"

SRC_PARENT="$PROJECT_ROOT/src"
SRC_DIR="$SRC_PARENT/lufus"
GUI_DIR="$SRC_DIR/gui"
MAIN_SCRIPT="$SRC_DIR/__main__.py"

# ---------- Validate source paths ----------
if [ ! -d "$SRC_PARENT" ]; then
    echo "ERROR: Source parent directory not found: $SRC_PARENT"
    echo "Please run this script from the project root (where src/ is located)."
    exit 1
fi
if [ ! -d "$SRC_DIR" ]; then
    echo "ERROR: lufus package directory not found: $SRC_DIR"
    exit 1
fi
if [ ! -f "$MAIN_SCRIPT" ]; then
    echo "ERROR: Main script not found: $MAIN_SCRIPT"
    exit 1
fi
if [ ! -d "$GUI_DIR" ]; then
    echo "ERROR: gui directory not found: $GUI_DIR"
    exit 1
fi
echo "✅ Source paths verified."

APPIMAGE_NAME="lufus-x86_64.AppImage"
LINUXDEPLOY_URL="https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage"
LINUXDEPLOY_QT_URL="https://github.com/linuxdeploy/linuxdeploy-plugin-qt/releases/download/continuous/linuxdeploy-plugin-qt-x86_64.AppImage"

# Prerequisites
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 required"; exit 1; }
command -v pip >/dev/null 2>&1 || { echo "❌ pip required"; exit 1; }

# Install dependencies
pip install --upgrade pyinstaller pyqt6 psutil pyudev

# Download linuxdeploy (if missing)
[ -f linuxdeploy-x86_64.AppImage ] || wget "$LINUXDEPLOY_URL"
[ -f linuxdeploy-plugin-qt-x86_64.AppImage ] || wget "$LINUXDEPLOY_QT_URL"
chmod +x linuxdeploy*.AppImage

# Clean previous builds
rm -rf build dist AppDir

# ---------- PyInstaller ----------
echo "🚀 Running PyInstaller..."
pyinstaller "$MAIN_SCRIPT" \
    --name lufus \
    --windowed \
    --paths "$SRC_PARENT" \
    --strip \
    --exclude-module tkinter \
    --collect-all PyQt6 \
    --collect-all psutil \
    --collect-all lufus \
    --hidden-import lufus.drives.autodetect_usb \
    --hidden-import lufus.drives.states \
    --hidden-import lufus.drives.find_usb \
    --hidden-import lufus.drives.formatting \
    --hidden-import lufus.gui.gui \
    --hidden-import lufus.gui.start_gui \
    --hidden-import lufus.writing.flash_usb \
    --hidden-import lufus.writing.flash_woeusb \
    --hidden-import lufus.writing.check_file_sig \
    --hidden-import lufus.writing.detect_windows \
    --hidden-import lufus.writing.flash_windows \
    --hidden-import lufus.writing.install_ventoy \
    --add-data "$GUI_DIR/themes:themes" \
    --add-data "$GUI_DIR/languages:languages" \
    --add-data "$GUI_DIR/assets:assets" \
    --noconfirm

# ---------- Verify bundle ----------
echo "=== Bundle Contents (first 3 levels) ==="
if [ -d "dist/lufus" ]; then
    if command -v tree &> /dev/null; then
        tree -L 3 dist/lufus/
    else
        print_tree dist/lufus/ 3
    fi
else
    echo "❌ dist/lufus/ directory not found!"
    ls -la dist/
    exit 1
fi
echo "========================================"

# Locate gui module
GUI_LOCATION=$(find dist/lufus -type d -name "gui" 2>/dev/null | head -1)
if [ -n "$GUI_LOCATION" ]; then
    echo "✅ gui module found at: $GUI_LOCATION"
else
    echo "❌ ERROR: gui module not found anywhere in dist/lufus/"
    echo "This means PyInstaller failed to include lufus.gui.gui."
    echo "🔍 Dumping extra debug info:"
    echo "--- First 20 .pyc files found ---"
    find dist/lufus -type f -name "*.pyc" | head -20
    echo "--- Directories named 'lufus' ---"
    find dist/lufus -type d -name "lufus" 2>/dev/null
    echo "--- Full recursive listing (first 100 lines) ---"
    find dist/lufus -print | head -100
    exit 1
fi

# Locate data folders
for folder in themes languages assets; do
    if [ -d "dist/lufus/$folder" ]; then
        echo "✅ $folder found at dist/lufus/$folder"
    elif [ -d "dist/lufus/_internal/$folder" ]; then
        echo "✅ $folder found at dist/lufus/_internal/$folder"
    else
        echo "⚠️  WARNING: $folder not found in dist/lufus/ or dist/lufus/_internal/"
    fi
done

# ---------- Build AppDir ----------
mkdir -p AppDir/usr/bin
cp -r dist/lufus/* AppDir/usr/bin/

# .desktop and icon
DESKTOP_SOURCE="$GUI_DIR/lufus.desktop"
ICON_SOURCE="$GUI_DIR/assets/lufus.png"

if [ -f "$DESKTOP_SOURCE" ]; then
    cp "$DESKTOP_SOURCE" AppDir/
else
    cat > AppDir/lufus.desktop <<EOF
[Desktop Entry]
Name=lufus
Exec=lufus
Icon=lufus
Type=Application
Categories=Utility;
EOF
fi

if [ -f "$ICON_SOURCE" ]; then
    cp "$ICON_SOURCE" AppDir/
else
    echo "⚠️  Warning: lufus.png not found – icon will be missing."
fi

# ---------- Build AppImage ----------
ARCH=x86_64 ./linuxdeploy-x86_64.AppImage \
    --appdir AppDir \
    --executable AppDir/usr/bin/lufus \
    --desktop-file AppDir/lufus.desktop \
    --icon-file AppDir/lufus.png \
    --output appimage

ls -lh "$APPIMAGE_NAME"
echo "✅ AppImage created successfully."
