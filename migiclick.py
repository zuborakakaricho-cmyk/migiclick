#!/usr/bin/env python3
"""右クリックで事務：ファイルを右クリックして、事務の作業を1回で済ませる道具（Mac・Windows）。

使い方（右クリックのメニューから呼ばれる。手で試すときも同じ）:
  python3 migiclick.py gijiroku   録音.m4a ...   … 議事録にする（文字起こしは手元。議事録にするところだけClaude Code）
  python3 migiclick.py gijiroku   メモ.txt ...   … メモや文字起こし（.txt・Zoom/Teamsの.vtt）からも作れる
  python3 migiclick.py mojiokoshi 録音.m4a ...   … 文字起こしだけ（全部手元。外に何も送らない）
  python3 migiclick.py namae      請求書.pdf ... … 中身からファイル名を付ける（中身をClaude Codeに読ませる）
  python3 migiclick.py chiisaku   写真.jpg ...   … 申請用に小さくする（既定500KB以下。手元だけ）
  python3 migiclick.py ichi       写真.jpg ...   … 位置情報（GPS）を消す（手元だけ）
  python3 migiclick.py douga      動画.mov ...   … 動画の容量を減らす（送れる軽さのMP4。画面は短い辺720に。撮った場所も消える。手元だけ）
  python3 migiclick.py makase     ファイル ...   … まとめて選んだファイルを、種類に合わせて振り分ける
                                                  （録音・メモ→議事録、PDF→名前付け、写真→申請用に小さくする）
  python3 migiclick.py doctor                    … 要る道具がそろっているか確かめる

決まりごと:
- 元のファイルは上書きしない。できた物は同じフォルダに新しいファイルで置く（名前を付ける操作だけは、確かめてから名前を変える）
- 外に送るのは、メニューの名前に「Claude」と書いた操作だけ
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
IS_WIN = platform.system() == "Windows"
NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WIN else {}  # Windowsで、呼んだ道具の黒い窓を出さない
HOME = Path.home()
CACHE = (Path(os.environ.get("LOCALAPPDATA", HOME)) / "migiclick") if IS_WIN else HOME / ".cache" / "migiclick"
CONFIG_FILE = HERE / "config.json"
DEFAULTS = {
    "whisper_model": "base",          # base（142MB・速い）／small（466MB・正確）／large-v3-turbo-q5_0（547MB・いちばん正確で遅い）
    "max_kb": 500,                    # 申請用に小さくするときの上限
    "video_px": 720,                  # 動画の容量を減らすときの、画面の短い辺（720＝HD。1080にすると容量は増えるがきれい）
    "video_crf": 28,                  # 動画の画質（数が大きいほど容量が減り粗くなる。23で元に近い、28で送る用）
    "gijiroku_prompt": "次の文字起こし（または会議のメモ）から、議事録の下書きを作ってください。次の形で、Markdownで書く。\n会議名：〔記入〕　日時：〔記入〕　場所：〔記入〕\n出席者：〔記入〕（録音に出てきた名前：〇〇さん、〇〇さん）\n1. 決まったこと\n2. 宿題（誰が・何を・いつまでに。表にする）\n3. 決まらなかったこと（持ち越し・保留。無ければ「なし」）\n4. 話したこと（議題ごとに短く）\n5. 次回の予定（無ければ「なし」）\n※ 聞き取りに自信のない語（文字起こしの誤りを直した語と、直せなかった語）\n決まり：文字起こしに無いことは書かない。会議名・日時・場所・出席者は文字起こしからわからなければ〔記入〕のまま残す（録音に出てきた名前だけ括弧の中に書く）。聞き取れない所は〔不明〕と書く。録音ではなくメモから作るときは「※ 聞き取りに自信のない語」の欄は書かない。議事録だけを書き、前置き・後書き・こちらへの説明は書かない。",  # 変えたいときは config.json に gijiroku_prompt を書く
}
AUDIO = {".m4a", ".mp3", ".wav", ".aac", ".mp4", ".mov", ".m4v", ".caf", ".ogg", ".opus", ".flac", ".aiff", ".aif", ".webm", ".mkv"}
TEXT = {".txt", ".vtt"}  # 議事録はメモや文字起こしの文字からも作れる
IMAGE = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
VIDEO = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}


def cfg():
    c = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        c.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    return c


# ---------- 画面に知らせる（Macは通知とダイアログ、Windowsはメッセージボックス） ----------
def _ps(s):
    return s.replace("'", "''")


def notify(msg, title="右クリックで事務"):
    print(msg)
    if os.environ.get("MIGICLICK_QUIET"):
        return
    if IS_WIN:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Add-Type -AssemblyName System.Windows.Forms; [void][System.Windows.Forms.MessageBox]::Show('{_ps(msg)}','{_ps(title)}')"], **NOWIN)
    else:
        # 日本語は文に埋め込まず argv で渡す（json.dumps だと \uXXXX になり AppleScript が読めない）
        subprocess.run(["osascript", "-e", "on run argv",
                        "-e", 'display notification (item 1 of argv) with title (item 2 of argv) sound name "Glass"',
                        "-e", "end run", msg, title])


def ask_name(proposed, title="右クリックで事務"):
    """提案した名前を見せて、そのままか直した名前を返す。やめたら None。"""
    if os.environ.get("MIGICLICK_YES"):
        return proposed
    if IS_WIN:
        # 返ってくる名前を UTF-8 にする（そのままだと Windows PowerShell は Shift_JIS で返し、日本語が化ける）
        ps = ("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Add-Type -AssemblyName Microsoft.VisualBasic; "
              f"[Microsoft.VisualBasic.Interaction]::InputBox('この名前に変えます。直すならここで直してください','{_ps(title)}','{_ps(proposed)}')")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, encoding="utf-8", **NOWIN)
        out = r.stdout.strip()
        return out or None
    script = ('on run argv\n'
              'activate\n'  # ほかの窓の裏に隠れないよう、手前に出す
              'set r to display dialog "この名前に変えます。直すならここで直してください" default answer (item 1 of argv) '
              'with title (item 2 of argv) buttons {"やめる", "変える"} default button "変える"\n'
              'if button returned of r is "変える" then return text returned of r\nreturn ""\nend run')
    r = subprocess.run(["osascript", "-e", script, proposed, title], capture_output=True, text=True)
    return r.stdout.strip() or None


def new_path(p: Path, suffix_name: str, ext=None):
    """元の隣に「元の名前_〇〇.拡張子」。同じ名前があれば (2)(3)… を付ける"""
    ext = ext or p.suffix
    q = p.with_name(f"{p.stem}_{suffix_name}{ext}")
    n = 2
    while q.exists():
        q = p.with_name(f"{p.stem}_{suffix_name}({n}){ext}")
        n += 1
    return q


def reveal(paths):
    """できたファイルを、Finder（Windowsはエクスプローラー）で選んだ状態で見せる"""
    if os.environ.get("MIGICLICK_QUIET") or not paths:
        return
    if IS_WIN:
        subprocess.run(["explorer", "/select,", str(paths[0])])
    else:
        subprocess.run(["open", "-R", *[str(p) for p in paths]])


def find(cmd):
    w = shutil.which(cmd)
    if w:
        return w
    if IS_WIN:
        for d in [CACHE / "whisper", HOME / ".local" / "bin", Path(os.environ.get("APPDATA", "")) / "npm"]:
            for name in (cmd + ".exe", cmd + ".cmd"):
                if (d / name).exists():
                    return str(d / name)
    else:
        for d in ["/opt/homebrew/bin", "/usr/local/bin", str(HOME / ".local" / "bin")]:
            if Path(d, cmd).exists():
                return str(Path(d, cmd))
    return None


# ---------- Claude Code（議事録・名前付けで使う） ----------
def has_claude():
    return bool(find("claude")) and not os.environ.get("MIGICLICK_NO_CLAUDE")


def to_clipboard(text):
    try:
        subprocess.run(["clip"] if IS_WIN else ["pbcopy"], input=text.encode("utf-16-le" if IS_WIN else "utf-8"), check=True, **NOWIN)
        return True
    except Exception:
        return False


class ClaudeTimeout(RuntimeError):
    pass


def ask_claude(prompt, text, wait=120):
    claude = find("claude") if has_claude() else None
    if not claude:
        raise RuntimeError("Claude Code（claude コマンド）が見つかりません。入れていない場合、この操作は使えません")
    # 右クリックのあと何分も待たせないよう、wait 秒で打ち切る。
    # Claude Code が起こした子のプロセスまでまとめて止めないと、打ち切っても戻ってこないことがある
    # 頼み方も中身も標準入力で渡す（Windows の claude は claude.cmd で cmd.exe を通るので、引数だと改行で切れる）
    p = subprocess.Popen([claude, "-p"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", start_new_session=not IS_WIN, **NOWIN)
    try:
        out, err = p.communicate(f"{prompt}\n\n{text}", timeout=wait)
    except subprocess.TimeoutExpired:
        if IS_WIN:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, **NOWIN)
        else:
            import signal
            os.killpg(p.pid, signal.SIGKILL)
        p.wait()
        raise ClaudeTimeout(f"Claude Code が{wait}秒たっても返事をしませんでした")
    if p.returncode != 0:
        raise RuntimeError("Claude Code が止まりました：" + (err or out)[-300:])
    return out.strip()


# ---------- 文字起こし（whisper.cpp・手元だけ） ----------
def model_path(name):
    p = CACHE / f"ggml-{name}.bin"
    if not p.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{name}.bin"
        notify(f"初回だけ、文字起こしのモデル（{name}）を取ってきます。少し時間がかかります")
        tmp = p.with_suffix(".part")
        curl = find("curl")  # Mac・Windows 10以降に最初から入っている。Pythonの証明書の設定に左右されない
        if curl:
            subprocess.run([curl, "-fsSL", "-o", str(tmp), url], check=True, **NOWIN)
        else:
            urllib.request.urlretrieve(url, tmp)
        tmp.rename(p)
    return p


# ---------- 長い録音：始めた時点でかかる時間の見込みを知らせる ----------
LONG_MIN = 10                         # これより長い録音には、文字起こしを飛ばせる方法も案内する
SPEED_FILE = CACHE / "speed.json"     # このパソコンで前に測った「文字起こしの時間÷録音の長さ」


def audio_seconds(audio: Path):
    """録音の長さ（秒）。わからなければ None"""
    try:
        import av  # faster-whisper と一緒に入る
        with av.open(str(audio)) as c:
            if c.duration:
                return c.duration / 1_000_000
    except Exception:
        pass
    ffprobe = find("ffprobe")
    if ffprobe:
        r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio)],
                           capture_output=True, text=True, **NOWIN)
        try:
            return float(r.stdout.strip())
        except ValueError:
            pass
    return None


def speed_ratio():
    try:
        return float(json.loads(SPEED_FILE.read_text(encoding="utf-8"))["ratio"])
    except Exception:
        return 0.2  # 測ったことが無いときの見込み（2020年のIntelのMac・baseで約0.18だった）


def save_speed(sec, took):
    if sec < 30:  # 短い録音は、モデルを読む時間の割合が大きく、見込みがずれるので覚えない
        return
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        SPEED_FILE.write_text(json.dumps({"ratio": round(took / sec, 3)}), encoding="utf-8")
    except OSError:
        pass


def model_cached():
    """文字起こしのモデルがもう手元にあるか（初回は取ってくる時間がかかる）"""
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return (CACHE / f"ggml-{cfg()['whisper_model']}.bin").exists()
    name = FW_MODELS.get(cfg()["whisper_model"], cfg()["whisper_model"])
    return any((CACHE / "fw").glob(f"models--Systran--faster-whisper-{name}*"))


def start_message(sec):
    est = sec * speed_ratio()
    end = "1分かからずに終わる見込みです" if est < 60 else f"約{round(est / 60)}分かかる見込みです"
    msg = f"文字起こし中です。{round(sec / 60)}分の録音で、{end}"
    if sec >= LONG_MIN * 60:
        msg += "\n長い会議は、iPhoneのボイスメモやZoom・Teamsの文字起こし（.txt・.vtt）を右クリックすると、文字起こしを飛ばせて早く終わります"
    return msg


FW_MODELS = {"base": "base", "small": "small", "large-v3-turbo-q5_0": "large-v3-turbo", "large-v3-turbo": "large-v3-turbo"}


def transcribe(audio: Path):
    """長さを測って見込みを知らせてから、文字にする。かかった時間は次の見込みに使う"""
    sec = audio_seconds(audio)
    if sec and sec >= 60:  # 1分より短い録音はすぐ終わるので知らせない
        notify(start_message(sec))
    cached = model_cached()
    t0 = time.time()
    text = _transcribe(audio)
    if sec and cached:  # モデルを取ってきた回は、その時間が混ざって見込みが大きくずれるので覚えない
        save_speed(sec, time.time() - t0)
    return text


def _transcribe(audio: Path):
    """faster-whisper があればそれで（ffmpeg も要らない）。無ければ whisper.cpp（whisper-cli＋ffmpeg）で"""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        WhisperModel = None
    if WhisperModel:
        try:
            import certifi  # 道具専用のPythonでも、モデルを取ってくるときに証明書で止まらないように
            os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        except ImportError:
            pass
        name = FW_MODELS.get(cfg()["whisper_model"], cfg()["whisper_model"])
        if not model_cached():
            notify(f"初回だけ、文字起こしのモデル（{name}）を取ってきます。少し時間がかかります")
        model = WhisperModel(name, device="cpu", compute_type="int8", download_root=str(CACHE / "fw"))
        segs, _ = model.transcribe(str(audio), language="ja", vad_filter=True)
        return "".join(s.text for s in segs).strip()
    ffmpeg, whisper = find("ffmpeg"), find("whisper-cli")
    if not ffmpeg or not whisper:
        raise RuntimeError("文字起こしの部品が見つかりません。入れる用のファイルで入れ直してください")
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "in.wav"
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(audio), "-ar", "16000", "-ac", "1", str(wav)], check=True, **NOWIN)
        out = Path(td) / "out"
        subprocess.run([whisper, "-m", str(model_path(cfg()["whisper_model"])), "-l", "ja", "-nt", "-otxt", "-of", str(out), "-f", str(wav)],
                       check=True, capture_output=True, **NOWIN)
        return (out.with_suffix(".txt")).read_text(encoding="utf-8").strip()


def do_mojiokoshi(f: Path):
    text = transcribe(f)
    q = new_path(f, "文字起こし", ".txt")
    q.write_text(text + "\n", encoding="utf-8")
    return q


def read_text(f: Path):
    """メモ帳のShift_JISで保存した物も読めるように、順に試す"""
    b = f.read_bytes()
    for enc in ("utf-8-sig", "cp932", "utf-16"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    raise RuntimeError("文字の形式が読めませんでした（UTF-8かShift_JISで保存し直してください）")


def vtt_to_text(s):
    """Zoom・Teamsの字幕形式（.vtt）から、時刻や番号を抜いて「話した人：中身」の行だけにする"""
    lines, prev = [], None
    for block in re.split(r"\n\s*\n", s.replace("\r\n", "\n")):
        body = [l for l in block.strip().split("\n") if l.strip()]
        if not body or body[0].startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        times = [i for i, l in enumerate(body) if "-->" in l]
        if times:  # 時刻の行より前は番号（Teamsは a1b2-…/12-0 のような形）なので、時刻の後だけ使う
            body = body[times[0] + 1:]
        for l in body:
            m = re.match(r"<v\s+([^>]+)>(.*?)(?:</v>)?$", l.strip())  # Teams は <v 名前>中身</v>
            l = f"{m.group(1).strip()}：{m.group(2)}" if m else l.strip()
            l = re.sub(r"<[^>]+>", "", l)
            if l and l != prev:  # 字幕の切れ目で同じ行が続くことがあるので1つにする
                lines.append(l)
                prev = l
    return "\n".join(lines)


def do_gijiroku(f: Path):
    if f.suffix.lower() in TEXT:  # メモや文字起こしの文字なら、文字起こしは飛ばす
        text = read_text(f)
        if f.suffix.lower() == ".vtt":
            text = vtt_to_text(text)
        text = text.strip()
        if not text:
            raise RuntimeError("中身が空でした")
    else:
        text = transcribe(f)
        t = new_path(f, "文字起こし", ".txt")
        t.write_text(text + "\n", encoding="utf-8")
    why = None if has_claude() else "Claude Code が無い"
    wait = max(300, len(text) // 50)  # 5分。長い会議の文字（1万5千字を超える）なら、文字の量に合わせて延ばす
    if not why:
        try:
            memo = ask_claude(cfg()["gijiroku_prompt"], text, wait=wait)
        except ClaudeTimeout:
            why = f"Claude Code の返事が{wait // 60}分たっても来なかった"
    if why:  # Claude Code が使えないときは、ChatGPTなどに貼る文を作る
        req = cfg()["gijiroku_prompt"] + "\n\n--- 文字起こし ---\n" + text + "\n"
        q = new_path(f, "議事録の頼み方", ".txt")
        q.write_text(req, encoding="utf-8")
        copied = to_clipboard(req)
        return q, (f"（{why}ので、ChatGPTなどに貼る文を作りました" + ("。コピー済みです）" if copied else "）"))
    q = new_path(f, "議事録", ".md")
    q.write_text(memo + "\n", encoding="utf-8")
    return q


# ---------- 中身からファイル名を付ける ----------
NAME_PROMPT = ("次の書類の文字から、ファイル名に使う情報をJSONだけで返してください。"
               '形は {"kind":"書類の種類（請求書・見積書・納品書・領収書・契約書 など）","date":"YYYYMMDD（書類の日付。無ければ空）","party":"相手の会社名（自分宛てなら発行元）","amount":"合計金額の数字だけ（無ければ空）"}。'
               "書類に無いことは推測せず空にする。")
BAD = re.compile(r'[\\/:*?"<>|\r\n\t]')


def pdf_text(f: Path):
    exe = find("pdftotext")
    if exe:
        # -enc UTF-8：Windowsの pdftotext（Git for Windows に入っている物など）は既定が Latin1 で、日本語が消える
        r = subprocess.run([exe, "-layout", "-enc", "UTF-8", "-l", "3", str(f), "-"], capture_output=True, **NOWIN)
        text = r.stdout.decode("utf-8", "ignore")
    else:
        try:
            from pypdf import PdfReader
        except ImportError:
            raise RuntimeError("PDFの文字を取る道具（pdftotext か pypdf）がありません")
        text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(f)).pages[:3])
    # PDFによっては「日」「月」「文」が見た目の同じ部首の文字（⽇⽉⽂）で出てくるので、普通の文字にそろえる
    import unicodedata
    return unicodedata.normalize("NFKC", text)


KINDS = ["請求書", "見積書", "納品書", "領収書", "注文書", "契約書"]
COMPANY = re.compile(r"((?:株式会社|有限会社|合同会社)\s*[^\s　、。御様\d]{1,20}|[^\s　、。\d]{1,20}\s*(?:株式会社|有限会社|合同会社))")


def guess_info(text):
    """Claude を使わずに、書類によくある形から拾う。拾えなかった所は空のまま"""
    info = {"kind": "", "date": "", "party": "", "amount": ""}
    head = text[:400]
    info["kind"] = next((k for k in KINDS if k in head.replace(" ", "")), next((k for k in KINDS if k in text), ""))
    m = re.search(r"(20\d{2})\s*[年/.\-]\s*(\d{1,2})\s*[月/.\-]\s*(\d{1,2})", text)
    if m:
        info["date"] = f"{m.group(1)}{int(m.group(2)):02d}{int(m.group(3)):02d}"
    m = re.search(r"(?:ご?請求金額|お?見積金額|合計金額|お?支払金額|税込合計|合計)[^\d\n]{0,10}([\d,]{3,})", text)
    if m:
        info["amount"] = m.group(1).replace(",", "")
    for line in text.splitlines():  # 宛先（御中・様の行）でない会社名を、発行元とみなす
        if "御中" in line or "様" in line:
            continue
        m = COMPANY.search(line)
        if m:
            info["party"] = re.sub(r"\s+", "", m.group(1))
            break
    return info


def propose_name(info, ext):
    parts = [info.get("date", ""), info.get("party", ""), info.get("kind", "")]
    amt = re.sub(r"[^\d]", "", str(info.get("amount", "")))
    if amt:
        parts.append(f"{int(amt):,}円")
    name = "_".join(BAD.sub("", p).strip() for p in parts if p and str(p).strip())
    return (name[:80] + ext) if name else None


def do_namae(f: Path):
    text = pdf_text(f) if f.suffix.lower() == ".pdf" else f.read_text(encoding="utf-8", errors="ignore")
    if len(text.strip()) < 10:
        raise RuntimeError(f"{f.name}：文字が読めませんでした（画像だけのPDFかもしれません）")
    info = None
    if has_claude():
        try:
            raw = ask_claude(NAME_PROMPT, text[:6000])
        except ClaudeTimeout:
            raw = ""  # 返事が来なければ、手元で拾う形に切り替える
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            info = json.loads(m.group(0))
        elif raw:
            raise RuntimeError("名前の案を作れませんでした：" + raw[:200])
    if info is None:  # Claude Code が無い・返事が無いときは、日付・金額・種類・会社名を決まった形から拾う（外に送らない）
        info = guess_info(text)
    name = propose_name(info, f.suffix)
    if not name:
        raise RuntimeError("書類から日付・相手・金額を読み取れませんでした")
    name = ask_name(name)
    if not name:
        return None
    name = BAD.sub("", name)
    if not name.lower().endswith(f.suffix.lower()):
        name += f.suffix
    q = f.with_name(name)
    n = 2
    while q.exists() and q != f:
        q = f.with_name(f"{Path(name).stem}({n}){f.suffix}")
        n += 1
    f.rename(q)
    return q


# ---------- 画像（手元だけ） ----------
def open_image(f: Path, turn=True):
    from PIL import Image, ImageOps
    if f.suffix.lower() == ".heic":
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            raise RuntimeError("HEICを開くには pillow-heif が要ります（pip install pillow-heif）")
    im = Image.open(f)
    return ImageOps.exif_transpose(im) if turn else im  # 向きを正しくしてから扱う


def do_chiisaku(f: Path):
    from PIL import Image
    limit = int(cfg()["max_kb"]) * 1024
    im = open_image(f).convert("RGB")
    q = new_path(f, f"{cfg()['max_kb']}KB以下", ".jpg")
    scale, quality = 1.0, 90
    for _ in range(30):
        w, h = int(im.width * scale), int(im.height * scale)
        im.resize((w, h), Image.LANCZOS).save(q, "JPEG", quality=quality, optimize=True)
        if q.stat().st_size <= limit:
            return q
        if quality > 60:
            quality -= 10
        else:
            scale *= 0.85
    raise RuntimeError(f"{f.name}：{cfg()['max_kb']}KB以下にできませんでした")


def do_ichi(f: Path):
    im = open_image(f, turn=False)  # iPhoneのHEICも開く。向きの情報はそのまま残す
    exif = im.getexif()
    had = 0x8825 in exif
    if 0x8825 in exif:
        del exif[0x8825]  # GPSの情報だけ消す（撮った日時などは残す）
    # XMP（写真アプリなどで編集すると付く）にも場所が入ることがあるので、XMPごと写さない
    had = had or "GPS" in str(im.info.get("xmp") or "")
    im.info.pop("xmp", None)
    q = new_path(f, "位置情報なし")
    fmt = im.format or "JPEG"
    kw = {"exif": exif.tobytes()} if fmt in ("JPEG", "MPO", "WEBP", "PNG") else {}
    if fmt == "JPEG":
        kw["quality"] = "keep"
    elif fmt == "MPO":
        # iPhoneのJPEGはMPO（写真が何枚か入った形）として開く。1枚目をJPEGにする。
        # "keep" はMPOに使えないので、同じ中身（元の画質の表とサンプリング）を渡す
        from PIL import JpegImagePlugin
        fmt = "JPEG"
        kw.update(qtables=im.quantization, subsampling=JpegImagePlugin.get_sampling(im))
    elif fmt == "HEIF":
        kw = {"exif": exif.tobytes(), "quality": 90}
    im.save(q, fmt, **kw)
    return q, had


# ---------- 動画（手元だけ。文字起こしと一緒に入る PyAV で縮める。ffmpeg は要らない） ----------
def do_douga(f: Path):
    import av
    side = int(cfg()["video_px"])
    sec = audio_seconds(f)
    if sec and sec >= 60:
        notify(f"動画の容量を減らしています。{round(sec / 60)}分の動画で、約{max(1, round(sec * 0.9 / 60))}分かかる見込みです")  # 2020年のIntelのMacで動画の長さの0.85倍ほど
    q = new_path(f, "軽量", ".mp4")
    try:
        # 元のメタデータ（撮った場所など）は写さない。向きだけは引き継ぐ
        with av.open(str(f)) as src, av.open(str(q), "w", options={"movflags": "faststart"}) as dst:
            if not src.streams.video:
                raise RuntimeError("映像が入っていません")
            vin = src.streams.video[0]
            ain = src.streams.audio[0] if src.streams.audio else None
            r = min(1.0, side / min(vin.width, vin.height))  # 短い辺を video_px（既定720）まで。小さい動画は大きくしない
            w, h = int(vin.width * r) // 2 * 2, int(vin.height * r) // 2 * 2
            vout = dst.add_stream("libx264", rate=vin.average_rate or 30)
            vout.width, vout.height, vout.pix_fmt = w, h, "yuv420p"
            vout.codec_context.time_base = vin.time_base
            vout.options = {"crf": str(cfg()["video_crf"]), "preset": "veryfast"}
            aout = dst.add_stream("aac", rate=ain.rate or 48000) if ain else None
            if aout:
                aout.bit_rate = 96_000
            turned = False
            for packet in src.demux(*[s for s in (vin, ain) if s]):
                for frame in packet.decode():
                    if packet.stream is vin:
                        if not turned:
                            vout.set_display_rotation(frame.rotation)  # iPhoneの縦動画が横倒しにならないように
                            turned = True
                        dst.mux(vout.encode(frame.reformat(w, h, "yuv420p")))
                    else:
                        frame.pts = None
                        dst.mux(aout.encode(frame))
            dst.mux(vout.encode())
            if aout:
                dst.mux(aout.encode())
    except BaseException:
        q.unlink(missing_ok=True)
        raise
    before, after = f.stat().st_size, q.stat().st_size
    if after >= before:
        q.unlink()
        raise RuntimeError("もう十分軽く、これ以上は容量が減りませんでした")
    return q, f"（{mb(before)}→{mb(after)}）"


def mb(n):
    return f"{n / 1024 / 1024:.1f}MB"


# ---------- 道具がそろっているか ----------
def doctor():
    """機能ごとに使えるかを出す。✕ はその機能が動かないときだけ（無くてよい道具は出さない）"""
    def has(mod):
        try:
            __import__(mod)
            return True
        except ImportError:
            return False
    fw = has("faster_whisper")
    rows = [
        ("文字起こし", fw or (find("whisper-cli") and find("ffmpeg")), "faster-whisper" if fw else "whisper-cli＋ffmpeg"),
        ("PDFの文字を読む", find("pdftotext") or has("pypdf"), "pdftotext" if find("pdftotext") else "pypdf"),
        ("写真", has("PIL"), "Pillow"),
        ("iPhoneの写真（HEIC）", has("pillow_heif"), "pillow-heif"),
        ("動画", has("av"), "PyAV"),
    ]
    for k, ok, how in rows:
        print(f"○ {k}（{how}）" if ok else f"✕ {k}：使う道具が見つかりません")
    if find("claude"):
        print("○ Claude Code（議事録・名前付けに使う）")
    else:
        print("－ Claude Code は入っていません。それでも7つとも動きます"
              "（議事録は頼み方をコピー、名前付けは手元で日付・会社名・金額を拾う形）")
    print(f"モデルの置き場所：{CACHE}")


ACTIONS = {"gijiroku": (AUDIO | TEXT, do_gijiroku, "議事録"), "mojiokoshi": (AUDIO, do_mojiokoshi, "文字起こし"),
           "namae": ({".pdf", ".txt"}, do_namae, "名前付け"), "chiisaku": (IMAGE, do_chiisaku, "小さくする"),
           "ichi": (IMAGE, do_ichi, "位置情報を消す"), "douga": (VIDEO, do_douga, "動画の容量を減らす")}


# まとめて選んだときの振り分け（上から順に、当てはまった1つだけ）。写真は小さくすると位置情報も消える
MAKASE = [("gijiroku", AUDIO | TEXT), ("namae", {".pdf"}), ("chiisaku", IMAGE)]


def pick(f: Path):
    return next((ACTIONS[a] for a, exts in MAKASE if f.suffix.lower() in exts), None)


def main(argv):
    if not argv or argv[0] not in ACTIONS and argv[0] not in ("doctor", "makase"):
        print(__doc__)
        return 2
    if argv[0] == "doctor":
        doctor()
        return 0
    makase = argv[0] == "makase"
    exts, fn, label = ACTIONS["gijiroku"] if makase else ACTIONS[argv[0]]
    files = [Path(a) for a in argv[1:]]
    if makase:  # 早く終わる写真・PDFを先に、時間のかかる議事録を最後に
        first = {"chiisaku": 0, "namae": 1, "gijiroku": 2}
        files.sort(key=lambda f: first.get(next((a for a, e in MAKASE if f.suffix.lower() in e), ""), 3))
        label = "まとめて"
    done, errors, made = [], [], []
    for f in files:
        if makase:
            hit = pick(f)
            if not hit:
                errors.append(f"{f.name}：振り分け先の無い種類なので、そのままにしました")
                continue
            exts, fn, _ = hit
        if f.suffix.lower() not in exts:
            errors.append(f"{f.name}：この操作では使えない種類のファイルです")
            continue
        try:
            r = fn(f)
            if isinstance(r, tuple):
                q, extra = r
                if extra is True:
                    extra = ""
                elif extra is False:
                    extra = "（もともと位置情報はありませんでした）"
                done.append(q.name + extra)
                made.append(q)
            elif r:
                done.append(r.name)
                made.append(r)
        except Exception as e:  # 1つ失敗しても残りは続ける
            errors.append(f"{f.name}：{e}")
    msg = (f"{label}：{len(done)}件できました " + "、".join(done)) if done else f"{label}：できた物はありません"
    if errors:
        msg += "\n" + "\n".join(errors)
    reveal(made)
    notify(msg)
    return 1 if errors and not done else 0


if __name__ == "__main__":
    if sys.stdout is None or sys.stderr is None:  # Windowsの右クリック（窓の無い pythonw）。モデルを取るときの進み具合などで落ちないよう、ログへ書く
        CACHE.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(CACHE / "migiclick.log", "a", encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
