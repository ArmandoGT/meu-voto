# OCR de uma imagem com o motor nativo do Windows (Windows.Media.Ocr, pt-BR). Uso: ocr_windows.ps1 <imagem.png>
# Escreve o texto em UTF-8 na saida padrao, uma linha por linha reconhecida. Usado por fetch_alero_atas.py.
param([string]$Imagem)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Esperar($op, [Type]$tipo) {
    $t = $asTask.MakeGenericMethod($tipo).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result
}
$arq = Esperar ([Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path $Imagem).Path)) ([Windows.Storage.StorageFile])
$fluxo = Esperar ($arq.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$dec = Esperar ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($fluxo)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bmp = Esperar ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$motor = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new("pt-BR"))
$res = Esperar ($motor.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
# remonta as linhas pela posicao das palavras (o motor separa uma linha da folha em varios pedacos)
$palavras = foreach ($l in $res.Lines) { foreach ($w in $l.Words) { $r = $w.BoundingRect
    [pscustomobject]@{ T = $w.Text; X = $r.X; Y = $r.Y + $r.Height / 2; H = $r.Height } } }
$linhas = New-Object System.Collections.ArrayList
foreach ($w in ($palavras | Sort-Object Y)) {
    $ult = if ($linhas.Count) { $linhas[$linhas.Count - 1] } else { $null }
    if ($ult -and [Math]::Abs($w.Y - $ult.Y) -lt [Math]::Max(8, 0.5 * $w.H)) { $null = $ult.W.Add($w) }
    else { $null = $linhas.Add([pscustomobject]@{ Y = $w.Y; W = (New-Object System.Collections.ArrayList) }); $null = $linhas[$linhas.Count - 1].W.Add($w) }
}
foreach ($l in $linhas) { ($l.W | Sort-Object X | ForEach-Object { $_.T }) -join " " }
$fluxo.Dispose()
