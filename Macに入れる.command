#!/bin/bash
# 右クリックで事務：Macに入れる（ダブルクリックで動く。「開けません」と止められたら、はじめにお読みください.txt の手順で）
# 入れる場所：~/Library/Application Support/migiclick（このフォルダは、入れたあと消してもかまいません）
# 管理者のパスワードは要りません。Homebrew もいりません。
set -e
cd "$(dirname "$0")"
SRC="$(pwd)"
APP="$HOME/Library/Application Support/migiclick"
PYV="3.12.15"; PBS="20261020"
case "$(uname -m)" in arm64) ARCH=aarch64;; *) ARCH=x86_64;; esac
echo "右クリックで事務 を入れます（5分ほどかかります。この窓は閉じずに待ってください）"
mkdir -p "$APP"
if [ ! -x "$APP/python/bin/python3" ]; then
  echo "1/4 道具専用のPythonを取ってきます…"
  curl -fsSL -o "$APP/python.tar.gz" "https://github.com/astral-sh/python-build-standalone/releases/download/$PBS/cpython-$PYV+$PBS-$ARCH-apple-darwin-install_only.tar.gz"
  tar -xzf "$APP/python.tar.gz" -C "$APP" && rm "$APP/python.tar.gz"
fi
PY="$APP/python/bin/python3"
echo "2/4 文字起こし・画像・PDFの部品を入れます…"
# av は 19 で open() の metadata_errors が無くなり、faster-whisper 1.2.1 が録音を読めなくなるので 18 までに止める
"$PY" -m pip install --quiet --disable-pip-version-check faster-whisper "av<19" pillow pillow-heif pypdf certifi
echo "3/4 文字起こしのモデルを取ってきます（約140MB・初回だけ）…"
cp "$SRC/migiclick.py" "$APP/"
[ -f "$APP/config.json" ] || cp "$SRC/config.sample.json" "$APP/config.json"
mkdir -p "$APP/mac" && cp "$SRC/mac/install.py" "$SRC/mac/template.wflow" "$APP/mac/"
MIGICLICK_QUIET=1 "$PY" -c "
import sys; sys.path.insert(0, '$APP')
import migiclick, certifi, os
os.environ.setdefault('SSL_CERT_FILE', certifi.where())
from faster_whisper import WhisperModel
WhisperModel(migiclick.FW_MODELS.get(migiclick.cfg()['whisper_model'],'base'), device='cpu', compute_type='int8', download_root=str(migiclick.CACHE / 'fw'))
print('モデルの用意ができました')"
echo "4/4 右クリックのメニューを入れます…"
"$PY" "$APP/mac/install.py"
"$PY" "$APP/migiclick.py" doctor
echo
echo "入れ終わりました。この窓は閉じてかまいません。"
echo "ファイルを右クリック →「クイックアクション」から使えます。出ないときはFinderを開き直してください。"
