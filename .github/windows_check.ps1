# 右クリックに登録された命令そのままで、試しのファイルに6つの操作と「送る」のまとめてをかけ、できた物を確かめる
#   pwsh .github/windows_check.ps1 [-Work 作業の場所]
param([string]$Work = $env:RUNNER_TEMP)
$ErrorActionPreference = 'Stop'
$env:MIGICLICK_QUIET = '1'; $env:MIGICLICK_YES = '1'; $env:MIGICLICK_NO_CLAUDE = '1'
$py = "$env:LOCALAPPDATA\migiclick\python\python.exe"
$w = Join-Path $Work 'menu'; $b = Join-Path $Work 'sendto'
foreach ($d in $w, $b) { New-Item -ItemType Directory -Force $d | Out-Null; Copy-Item '試しのファイル\*' $d }
& $py -m pip install --quiet --disable-pip-version-check numpy  # 試しの動画を作るのに使う
$mk = Join-Path $env:RUNNER_TEMP 'mk.py'
Set-Content $mk -Encoding utf8 -Value @'
import sys, av, numpy as np
with av.open(sys.argv[1], "w") as c:
    s = c.add_stream("libx264", rate=30); s.width, s.height, s.pix_fmt = 1280, 720, "yuv420p"
    for i in range(90):
        img = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
        for p in s.encode(av.VideoFrame.from_ndarray(img, format="rgb24")): c.mux(p)
    for p in s.encode(): c.mux(p)
'@
& $py $mk (Join-Path $w '画面録画.mp4')

function Run-Line($line) {
  $m = [regex]::Match($line, '^"([^"]+)"\s+(.*)$')
  $p = Start-Process -FilePath $m.Groups[1].Value -ArgumentList $m.Groups[2].Value -Wait -PassThru
  if ($p.ExitCode -ne 0) {
    Get-Content "$env:LOCALAPPDATA\migiclick\migiclick.log" -Tail 40 -ErrorAction SilentlyContinue
    throw "失敗しました（$($p.ExitCode)）：$line"
  }
}
function Menu($file, $action) {
  $ext = [IO.Path]::GetExtension($file)
  $k = "HKCU:\Software\Classes\SystemFileAssociations\$ext\shell\migiclick\shell"
  $sub = Get-ChildItem $k | Where-Object { $_.PSChildName -like "*_$action" }
  if (-not $sub) { throw "$ext の右クリックに $action がありません" }
  $label = (Get-ItemProperty $sub.PSPath).MUIVerb
  $cmd = (Get-ItemProperty "$($sub.PSPath)\command").'(default)'
  Write-Host "▶ $label（$ext）"
  Run-Line $cmd.Replace('%1', (Join-Path $w $file))
}
function Made($pattern, $dir = $w) {
  $f = Get-ChildItem $dir -Filter $pattern
  if (-not $f) { throw "できていません：$pattern" }
  $f | ForEach-Object { Write-Host "  ✓ $($_.Name)（$([math]::Round($_.Length / 1KB))KB）" }
}
Menu '会議.m4a' 'mojiokoshi';    Made '会議_文字起こし.txt'
Get-Content (Join-Path $w '会議_文字起こし.txt') -Encoding utf8
Menu '会議メモ.txt' 'gijiroku';  Made '会議メモ_議事録の頼み方.txt'
Menu 'Teams字幕.vtt' 'gijiroku'; Made 'Teams字幕_議事録の頼み方.txt'
Menu 'scan_0012.pdf' 'namae';    Made '*みどり文具*請求書*.pdf'
Menu '架空の写真.jpg' 'chiisaku'; Made '架空の写真_500KB以下.jpg'
Menu '架空の写真.jpg' 'ichi';     Made '架空の写真_位置情報なし.jpg'
Menu '画面録画.mp4' 'douga';      Made '画面録画_軽量.mp4'

Write-Host '▶ 送る →「まとめて種類に合わせる」'
$lnk = Join-Path ([Environment]::GetFolderPath('SendTo')) '右クリックで事務（まとめて種類に合わせる）.lnk'
. (Join-Path $PSScriptRoot '..\windows\lnk.ps1')
$sc = [Migiclick.Lnk]::Read($lnk)
$files = 'scan_0012.pdf', '架空の写真.jpg', '会議メモ.txt' | ForEach-Object { '"' + (Join-Path $b $_) + '"' }
Run-Line ('"{0}" {1} {2}' -f $sc[0], $sc[1], ($files -join ' '))
Made '*みどり文具*請求書*.pdf' $b; Made '架空の写真_500KB以下.jpg' $b; Made '会議メモ_議事録の頼み方.txt' $b