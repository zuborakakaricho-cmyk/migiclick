#!/bin/bash
# 右クリックで事務：Macから外す（ダブルクリックで動く）
APP="$HOME/Library/Application Support/migiclick"
if [ -x "$APP/python/bin/python3" ] && [ -f "$APP/mac/install.py" ]; then "$APP/python/bin/python3" "$APP/mac/install.py" --remove; fi
rm -rf "$APP" "$HOME/.cache/migiclick"
/System/Library/CoreServices/pbs -update
echo "外しました。この窓は閉じてかまいません。"
