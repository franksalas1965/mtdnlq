# Sincroniza el plugin de desarrollo con la carpeta de plugins de QGIS (copia, sin admin).
$src = "D:\proyectos\AI\Analisis en lenguaje Natural\mtdnlq_qgis"
$dst = "$env:APPDATA\QGIS\QGIS3\profiles\default\python\plugins\mtdnlq_qgis"

if (-not (Test-Path $src)) {
    Write-Error "No existe: $src"
    exit 1
}

$pluginsDir = Split-Path $dst -Parent
if (-not (Test-Path $pluginsDir)) {
    New-Item -ItemType Directory -Path $pluginsDir -Force | Out-Null
}

robocopy $src $dst /MIR /XD __pycache__ .git /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
if ($LASTEXITCODE -ge 8) {
    Write-Error "robocopy falló con código $LASTEXITCODE"
    exit $LASTEXITCODE
}

Get-ChildItem -Path $dst -Recurse -Directory -Filter __pycache__ -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }

Write-Host "Plugin copiado a: $dst"
Write-Host "En QGIS: Complementos -> Desactivar MTD-NLQ -> Activar (o reiniciar QGIS)."
