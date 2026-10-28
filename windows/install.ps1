# 右クリックで事務：Windowsの右クリックにメニューを入れる・外す（試験的）
#   ふだんは「Windowsに入れる.cmd」「Windowsから外す.cmd」をダブルクリックする。中でこれを呼ぶ
#   powershell -ExecutionPolicy Bypass -File windows\install.ps1           … 入れる
#   powershell -ExecutionPolicy Bypass -File windows\install.ps1 -Remove   … 外す
# 入れる場所：%LOCALAPPDATA%\migiclick（このフォルダは、入れたあと消してもかまいません）
# 管理者の権限は要りません（自分のユーザーにだけ入れます）。Python も自分で入れなくてよい
param([switch]$Remove)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src  = Split-Path -Parent $here
$app  = Join-Path $env:LOCALAPPDATA 'migiclick'
$root = 'HKCU:\Software\Classes\SystemFileAssociations'
$sendto = Join-Path ([Environment]::GetFolderPath('SendTo')) '右クリックで事務（まとめて種類に合わせる）.lnk'
$pyv = '3.12.15'; $pbs = '20261020'
$audio = '.m4a','.mp3','.wav','.aac','.mp4','.mov','.m4v','.ogg','.opus','.flac','.aiff','.aif','.webm','.mkv'
$text  = '.txt','.vtt'  # 議事録はメモや文字起こしの文字からも作れる
$image = '.jpg','.jpeg','.png','.heic','.webp'
$video = '.mp4','.mov','.m4v','.mkv','.webm','.avi'
# （メニューの名前, 操作, ファイルの種類）。外に送る操作だけ名前に（Claude）と書く
# 「まとめて種類に合わせる」は右クリックの「送る」に入れる（右クリックのメニューは1つずつ別に動くので、まとめて渡せない）
$menus = @(
  @('議事録にする（Claude）',             'gijiroku',   ($audio + $text)),
  @('文字起こしだけ（パソコンの中だけ）', 'mojiokoshi', $audio),
  @('中身から名前を付ける（Claude）',     'namae',      @('.pdf')),
  @('申請用に小さくする',                 'chiisaku',   $image),
  @('位置情報を消す',                     'ichi',       $image),
  @('動画の容量を減らす',                 'douga',      $video)
)
$exts = $audio + $text + $image + $video + '.pdf' | Select-Object -Unique

function Remove-Menus {
  foreach ($ext in $exts) {
    $k = "$root\$ext\shell\migiclick"
    if (Test-Path -LiteralPath $k) { Remove-Item -LiteralPath $k -Recurse -Force }
  }
  if (Test-Path -LiteralPath $sendto) { Remove-Item -LiteralPath $sendto -Force }
}
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "$what に失敗しました（$LASTEXITCODE）" } }

if ($Remove) {
  Remove-Menus
  if (Test-Path -LiteralPath $app) { Remove-Item -LiteralPath $app -Recurse -Force }
  Write-Host '外しました。この窓は閉じてかまいません。'
  exit 0
}

Write-Host '右クリックで事務 を入れます（5分ほどかかります。この窓は閉じずに待ってください）'
New-Item -ItemType Directory -Force -Path $app | Out-Null
$py  = Join-Path $app 'python\python.exe'
$pyw = Join-Path $app 'python\pythonw.exe'  # 右クリックから動かすとき用（黒い窓を出さない）
if (-not (Test-Path -LiteralPath $py)) {
  Write-Host '1/4 道具専用のPythonを取ってきます…'
  $tgz = Join-Path $app 'python.tar.gz'
  curl.exe -fsSL -o $tgz "https://github.com/astral-sh/python-build-standalone/releases/download/$pbs/cpython-$pyv+$pbs-x86_64-pc-windows-msvc-install_only.tar.gz"
  Check 'Pythonの取得'
  tar.exe -xzf $tgz -C $app
  Check 'Pythonの展開'
  Remove-Item -LiteralPath $tgz -Force
}
Write-Host '2/4 文字起こし・画像・PDF・動画の部品を入れます…'
# av は 19 で open() の metadata_errors が無くなり、faster-whisper 1.2.1 が録音を読めなくなるので 18 までに止める
& $py -m pip install --quiet --disable-pip-version-check --no-warn-script-location faster-whisper 'av<19' pillow pillow-heif pypdf certifi
Check '部品のインストール'

Write-Host '3/4 文字起こしのモデルを取ってきます（約140MB・初回だけ）…'
Copy-Item -LiteralPath (Join-Path $src 'migiclick.py') -Destination $app -Force
$conf = Join-Path $app 'config.json'
if (-not (Test-Path -LiteralPath $conf)) { Copy-Item -LiteralPath (Join-Path $src 'config.sample.json') -Destination $conf }
$env:MIGICLICK_QUIET = '1'
& $py -c "import sys, os; sys.path.insert(0, sys.argv[1]); import migiclick, certifi; os.environ.setdefault('SSL_CERT_FILE', certifi.where()); from faster_whisper import WhisperModel; WhisperModel(migiclick.FW_MODELS.get(migiclick.cfg()['whisper_model'], 'base'), device='cpu', compute_type='int8', download_root=str(migiclick.CACHE / 'fw')); print('モデルの用意ができました')" $app
Check 'モデルの取得'
Remove-Item Env:\MIGICLICK_QUIET

Write-Host '4/4 右クリックのメニューを入れます…'
$tool = Join-Path $app 'migiclick.py'
Remove-Menus
foreach ($ext in $exts) {
  $items = @($menus | Where-Object { $_[2] -contains $ext })
  if (-not $items) { continue }
  $base = "$root\$ext\shell\migiclick"
  New-Item -Path $base -Force | Out-Null
  Set-ItemProperty -LiteralPath $base -Name 'MUIVerb' -Value '右クリックで事務'
  Set-ItemProperty -LiteralPath $base -Name 'SubCommands' -Value ''
  $i = 1
  foreach ($m in $items) {
    $k = "$base\shell\{0:D2}_{1}" -f $i, $m[1]
    New-Item -Path "$k\command" -Force | Out-Null
    Set-ItemProperty -LiteralPath $k -Name 'MUIVerb' -Value $m[0]
    Set-ItemProperty -LiteralPath "$k\command" -Name '(default)' -Value ('"{0}" "{1}" {2} "%1"' -f $pyw, $tool, $m[1])
    $i++
  }
}
# 「送る」の中に「まとめて種類に合わせる」。選んだファイルが全部まとめて渡る
$sc = (New-Object -ComObject WScript.Shell).CreateShortcut($sendto)
$sc.TargetPath = $pyw
$sc.Arguments = ('"{0}" makase' -f $tool)
$sc.Description = '録音・メモ→議事録、PDF→名前付け、写真→申請用に小さくする（Claude）'
$sc.Save()

& $py $tool doctor
Write-Host ''
Write-Host '入れ終わりました。この窓は閉じてかまいません。'
Write-Host 'ファイルを右クリック →（Windows 11は「その他のオプションを確認」）→「右クリックで事務」から使えます。'
Write-Host 'まとめて選んだときは、右クリック →（その他のオプションを確認）→「送る」→「右クリックで事務（まとめて種類に合わせる）」です。'
