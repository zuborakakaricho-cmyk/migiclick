# 外に送らない部分（字幕の読み取り・PDFからの名前付け・写真の縮小）を、試しのファイルで確かめる
import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("migiclick", ROOT / "migiclick.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SAMPLE = ROOT / "試しのファイル"


def test_vtt_zoom():
    text = m.vtt_to_text((SAMPLE / "Zoom字幕.vtt").read_text(encoding="utf-8"))
    assert text and "-->" not in text and "WEBVTT" not in text


def test_vtt_teams_speaker():
    text = m.vtt_to_text((SAMPLE / "Teams字幕.vtt").read_text(encoding="utf-8"))
    assert "：" in text and "<v" not in text


def test_pdf_name_without_claude():
    info = m.guess_info(m.pdf_text(SAMPLE / "scan_0012.pdf"))
    assert m.propose_name(info, ".pdf") == "20261015_株式会社みどり文具_請求書_68,200円.pdf"


def test_shrink_photo(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "notify", lambda *a, **k: None)
    monkeypatch.setattr(m, "reveal", lambda *a, **k: None)
    src = tmp_path / "写真.jpg"
    shutil.copy(SAMPLE / "架空の写真.jpg", src)
    m.do_chiisaku(src)
    out = list(tmp_path.glob("*500KB以下*"))
    assert out and out[0].stat().st_size <= 500 * 1024
    assert src.stat().st_size == (SAMPLE / "架空の写真.jpg").stat().st_size  # 元は上書きしない
