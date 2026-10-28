# 外に送らない部分（字幕の読み取り・PDFからの名前付け・写真の縮小）を、試しのファイルで確かめる
import importlib.util
import shutil
from pathlib import Path

import pytest

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


def test_makase_routes_by_type():
    assert m.pick(Path("会議.m4a"))[2] == "議事録"
    assert m.pick(Path("Zoom字幕.vtt"))[2] == "議事録"
    assert m.pick(Path("scan_0012.pdf"))[2] == "名前付け"
    assert m.pick(Path("写真.HEIC"))[2] == "小さくする"
    assert m.pick(Path("表.xlsx")) is None


def test_makase_photo_and_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "notify", lambda *a, **k: None)
    monkeypatch.setattr(m, "reveal", lambda *a, **k: None)
    monkeypatch.setattr(m, "has_claude", lambda: False)
    monkeypatch.setattr(m, "ask_name", lambda name, *a, **k: name)
    for n in ["架空の写真.jpg", "scan_0012.pdf"]:
        shutil.copy(SAMPLE / n, tmp_path / n)
    (tmp_path / "表.xlsx").write_text("x")
    assert m.main(["makase", *map(str, sorted(tmp_path.iterdir()))]) == 0
    names = {p.name for p in tmp_path.iterdir()}
    assert "架空の写真_500KB以下.jpg" in names
    assert "20261015_株式会社みどり文具_請求書_68,200円.pdf" in names
    assert "表.xlsx" in names  # 振り分け先の無いファイルは触らない


def test_long_recording_message(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "SPEED_FILE", tmp_path / "speed.json")
    assert m.speed_ratio() == 0.2  # 測ったことが無いときの見込み
    assert m.start_message(300) == "文字起こし中です。5分の録音で、約1分かかる見込みです"
    assert "iPhoneのボイスメモ" not in m.start_message(300)
    m.save_speed(600, 102)  # 10分の録音が102秒で終わった
    assert m.speed_ratio() == 0.17
    msg = m.start_message(3600)
    assert msg.startswith("文字起こし中です。60分の録音で、約10分かかる見込みです")
    assert "iPhoneのボイスメモ" in msg  # 10分以上なら、文字起こしを飛ばせる方法も案内する
    m.save_speed(10, 5)  # 短すぎる録音は覚えない
    assert m.speed_ratio() == 0.17


def test_shrink_video(tmp_path, monkeypatch):
    import av
    import numpy as np
    monkeypatch.setattr(m, "notify", lambda *a, **k: None)
    src = tmp_path / "縦動画.mov"
    with av.open(str(src), "w") as c:  # 画質最高で作り、撮った場所と縦向きの印を付ける
        c.metadata["location"] = "+34.6937+135.5023/"
        v = c.add_stream("libx264", rate=30)
        v.width, v.height, v.pix_fmt, v.options = 1280, 720, "yuv420p", {"crf": "0"}
        v.set_display_rotation(90)
        rng = np.random.default_rng(0)
        for _ in range(30):
            c.mux(v.encode(av.VideoFrame.from_ndarray(rng.integers(0, 255, (720, 1280, 3), dtype=np.uint8), format="rgb24")))
        c.mux(v.encode())
    size = src.stat().st_size
    q, extra = m.do_douga(src)
    assert q.name == "縦動画_軽量.mp4" and q.stat().st_size < size and "MB→" in extra
    assert src.stat().st_size == size  # 元は上書きしない
    with av.open(str(q)) as c:
        s = c.streams.video[0]
        assert (s.width, s.height) == (1280, 720) and s.frames == 30
        assert "location" not in c.metadata  # 撮った場所は写さない
        assert next(c.decode(s)).rotation == 90  # 縦動画のまま


def test_video_is_not_for_douga_in_makase():
    assert m.pick(Path("会議.mp4"))[2] == "議事録"  # まとめての中の動画は、これまでどおり議事録へ


# ---------- 位置情報を消す：iPhoneの写真（JPEGはMPOとして開く／HEICは編集するとXMPに場所が入る） ----------
XMP_GPS = (b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
           b'<rdf:Description xmlns:exif="http://ns.adobe.com/exif/1.0/" exif:GPSLatitude="34,41.5N"/></rdf:RDF></x:xmpmeta>')


def _exif_with_gps():
    from PIL import Image
    e = Image.Exif()
    e[0x0132] = "2026:10:01 12:00:00"  # 撮った日時
    e.get_ifd(0x8825)[2] = (34.0, 41.0, 30.0)
    return e


def _check_ichi(src):
    from PIL import Image
    q, had = m.do_ichi(src)
    out = Image.open(q)
    e = out.getexif()
    assert had
    assert 0x8825 not in e and b"GPSLatitude" not in q.read_bytes()  # 場所は消える
    assert e.get(0x0132) == "2026:10:01 12:00:00"  # 撮った日時は残る
    return out


def test_ichi_iphone_jpeg_mpo(tmp_path):
    from PIL import Image
    src = tmp_path / "IMG_0001.jpg"
    Image.new("RGB", (64, 48), "red").save(src, "MPO", save_all=True, append_images=[Image.new("RGB", (32, 24))],
                                           exif=_exif_with_gps(), xmp=XMP_GPS, quality=95)
    assert Image.open(src).format == "MPO"
    out = _check_ichi(src)
    assert out.format == "JPEG" and out.quantization == Image.open(src).quantization  # 画質は元のまま


def test_ichi_heic_xmp(tmp_path):
    pytest.importorskip("pillow_heif").register_heif_opener()
    from PIL import Image
    src = tmp_path / "IMG_0002.heic"
    Image.new("RGB", (64, 48), "red").save(src, "HEIF", exif=_exif_with_gps().tobytes(), xmp=XMP_GPS)
    assert b"GPSLatitude" in src.read_bytes()
    _check_ichi(src)


# ---------- 見込みの時間：モデルを取ってきた回は覚えない ----------
def test_speed_not_saved_on_first_download(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "SPEED_FILE", tmp_path / "speed.json")
    monkeypatch.setattr(m, "notify", lambda *a, **k: None)
    monkeypatch.setattr(m, "audio_seconds", lambda f: 120)
    monkeypatch.setattr(m, "_transcribe", lambda f: "文字")
    monkeypatch.setattr(m, "model_cached", lambda: False)
    m.transcribe(tmp_path / "会議.m4a")
    assert not (tmp_path / "speed.json").exists()
    monkeypatch.setattr(m, "model_cached", lambda: True)
    m.transcribe(tmp_path / "会議.m4a")
    assert (tmp_path / "speed.json").exists()


# ---------- Claude Code には、頼み方も中身も標準入力で渡す（Windowsで改行が切れないように） ----------
def test_ask_claude_sends_prompt_on_stdin(monkeypatch):
    seen = {}

    class FakePopen:
        returncode = 0
        pid = 0

        def __init__(self, args, **kw):
            seen["args"] = args

        def communicate(self, data, timeout=None):
            seen["stdin"] = data
            return "できた", ""

    monkeypatch.setattr(m, "has_claude", lambda: True)
    monkeypatch.setattr(m, "find", lambda name: "claude")
    monkeypatch.setattr(m.subprocess, "Popen", FakePopen)
    assert m.ask_claude("1行目\n2行目 & | > %", "中身") == "できた"
    assert seen["args"] == ["claude", "-p"]
    assert seen["stdin"] == "1行目\n2行目 & | > %\n\n中身"


def test_company_next_to_table_header():
    # Windowsの pdftotext では、表の見出しと会社名が同じ行に並ぶことがある
    info = m.guess_info("請求書\n品名   数量   単価   株式会社みどり文具\n2026年10月15日\nご請求金額 68,200円")
    assert info["party"] == "株式会社みどり文具"
    assert m.guess_info("みどり文具 株式会社\n")["party"] == "みどり文具株式会社"
