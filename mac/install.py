#!/usr/bin/env python3
"""Macの右クリック（Finderのクイックアクション）に「右クリックで事務」のメニューを入れる・外す。
  python3 mac/install.py            … 入れる
  python3 mac/install.py --remove   … 外す
入れたあと、ファイルを右クリック →「クイックアクション」か「サービス」の中に出ます。
"""
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE.parent / "migiclick.py"
SERVICES = Path.home() / "Library" / "Services"
PREFIX = "右クリックで事務 - "
# （メニューの名前, 操作, 右クリックに出すファイルの種類）。外に送る操作だけ名前に（Claude）と書く
MENUS = [
    ("議事録にする（Claude）", "gijiroku", ["public.audio", "public.movie", "public.plain-text", "org.w3.webvtt"]),
    ("文字起こしだけ（パソコンの中だけ）", "mojiokoshi", ["public.audio", "public.movie"]),
    ("中身から名前を付ける（Claude）", "namae", ["com.adobe.pdf"]),
    ("申請用に小さくする", "chiisaku", ["public.image"]),
    ("位置情報を消す", "ichi", ["public.image"]),
    ("まとめて種類に合わせる（Claude）", "makase",
     ["public.audio", "public.movie", "public.plain-text", "org.w3.webvtt", "com.adobe.pdf", "public.image"]),
]


def remove():
    for p in SERVICES.glob(PREFIX + "*.workflow"):
        shutil.rmtree(p)
        print("外しました：", p.name)


def install():
    SERVICES.mkdir(parents=True, exist_ok=True)
    tpl = plistlib.load(open(HERE / "template.wflow", "rb"))
    py = sys.executable  # 入れたときのPython（Pillowが入っているもの）で動かす
    for label, action, types in MENUS:
        wf = SERVICES / f"{PREFIX}{label}.workflow" / "Contents"
        wf.mkdir(parents=True, exist_ok=True)
        info = {"NSServices": [{"NSMenuItem": {"default": label}, "NSMessage": "runWorkflowAsService",
                                "NSSendFileTypes": types, "NSIconName": "NSActionTemplate"}]}
        plistlib.dump(info, open(wf / "Info.plist", "wb"))
        d = tpl.copy()
        d["actions"][0]["action"]["ActionParameters"]["COMMAND_STRING"] = f'"{py}" "{TOOL}" {action} "$@"'
        plistlib.dump(d, open(wf / "document.wflow", "wb"))
        print("入れました：", label)
    enable([m[0] for m in MENUS])
    subprocess.run(["/System/Library/CoreServices/pbs", "-update"])
    print("\nファイルを右クリック →「クイックアクション」（出ないときは「サービス」）から使えます。")
    print("まだ出ないときは、Finderを開き直してください（Optionを押しながらDockのFinderを右クリック →「再度開く」）。")


def enable(labels):
    """システム設定の「サービス」でオンにしたときと同じ印を付ける（付けないと右クリックに出ないことがある）"""
    out = subprocess.run(["defaults", "export", "pbs", "-"], capture_output=True).stdout
    d = plistlib.loads(out) if out else {}
    st = d.get("NSServicesStatus", {})
    for n in labels:
        st[f"(null) - {n} - runWorkflowAsService"] = {
            "enabled_context_menu": True, "enabled_services_menu": True,
            "presentation_modes": {"ContextMenu": True, "ServicesMenu": True, "FinderPreview": True, "TouchBar": False}}
    d["NSServicesStatus"] = st
    subprocess.run(["defaults", "import", "pbs", "-"], input=plistlib.dumps(d), check=True)


if __name__ == "__main__":
    remove() if "--remove" in sys.argv else install()
