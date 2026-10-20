param(
    [ValidateRange(1, 65535)][int]$Port = 8765,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath($PSScriptRoot)
$appId = 'explorador-campos-de-hielo'

$required = @(
    'index.html', 'app.js', 'style.css',
    'vendor/maplibre-gl.mjs', 'vendor/maplibre-gl.css',
    'vendor/maplibre-gl-worker.mjs', 'vendor/maplibre-gl-shared.mjs',
    'terrain/custom-layers.json', 'terrain/rgi-v6-outlines.geojson',
    'terrain/hydraulic-gradient-outlines.geojson'
)
foreach ($file in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $file) -PathType Leaf)) {
        throw "Falta un archivo del dashboard: $file"
    }
}

$mimeTypes = @{
    '.html' = 'text/html; charset=utf-8'
    '.css' = 'text/css; charset=utf-8'
    '.js' = 'text/javascript; charset=utf-8'
    '.mjs' = 'text/javascript; charset=utf-8'
    '.json' = 'application/json; charset=utf-8'
    '.geojson' = 'application/geo+json; charset=utf-8'
    '.png' = 'image/png'
    '.jpg' = 'image/jpeg'
    '.jpeg' = 'image/jpeg'
    '.svg' = 'image/svg+xml'
    '.webp' = 'image/webp'
    '.wasm' = 'application/wasm'
    '.pbf' = 'application/x-protobuf'
}

$listener = $null
$url = $null
for ($candidate = $Port; $candidate -le [Math]::Min($Port + 9, 65535); $candidate++) {
    $candidateUrl = "http://127.0.0.1:$candidate/"
    try {
        $status = Invoke-RestMethod -Uri "${candidateUrl}_explorador/status" -TimeoutSec 1
        if ($status.app -eq $appId -and $status.directory -eq $root) {
            Write-Output "El dashboard ya está abierto: $candidateUrl"
            if (-not $NoBrowser) { Start-Process $candidateUrl }
            exit 0
        }
    } catch { }

    $attempt = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Parse('127.0.0.1'), $candidate
    )
    try {
        $attempt.Start()
        $listener = $attempt
        $url = $candidateUrl
        break
    } catch {
        $attempt.Stop()
    }
}

if ($null -eq $listener) {
    throw 'No se pudo iniciar el servidor en ninguno de los diez puertos.'
}

Write-Output "Dashboard: $url"
Write-Output "Datos: $root"
Write-Output 'Ctrl+C cierra el dashboard.'
if (-not $NoBrowser) { Start-Process $url }

try {
    while ($true) {
        $client = $listener.AcceptTcpClient()
        try {
            $client.ReceiveTimeout = 5000
            $client.SendTimeout = 30000
            $stream = $client.GetStream()
            $reader = [System.IO.StreamReader]::new($stream, [System.Text.Encoding]::ASCII)
            $requestLine = $reader.ReadLine()
            if ([string]::IsNullOrEmpty($requestLine)) { continue }
            do { $header = $reader.ReadLine() } while ($null -ne $header -and $header.Length -gt 0)

            $parts = $requestLine.Split(' ')
            $method = $parts[0]
            $status = '200 OK'
            $contentType = 'application/octet-stream'
            $body = $null
            $path = $null
            $length = 0

            if ($parts.Length -lt 3 -or ($method -ne 'GET' -and $method -ne 'HEAD')) {
                $status = '405 Method Not Allowed'
            } else {
                $requestPath = ([System.Uri]::new($url.TrimEnd('/') + $parts[1])).AbsolutePath
                if ($requestPath -eq '/_explorador/status') {
                    $body = [System.Text.Encoding]::UTF8.GetBytes(
                        (@{ app = $appId; directory = $root } | ConvertTo-Json -Compress)
                    )
                    $contentType = 'application/json; charset=utf-8'
                    $length = $body.Length
                } else {
                    $relative = [System.Uri]::UnescapeDataString($requestPath.TrimStart('/'))
                    if ([string]::IsNullOrEmpty($relative)) { $relative = 'index.html' }
                    $path = [System.IO.Path]::GetFullPath((Join-Path $root $relative))
                    if (-not $path.StartsWith($root + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase) -or
                        -not [System.IO.File]::Exists($path)) {
                        $status = '404 Not Found'
                        $path = $null
                    } else {
                        $extension = [System.IO.Path]::GetExtension($path).ToLowerInvariant()
                        if ($mimeTypes.ContainsKey($extension)) { $contentType = $mimeTypes[$extension] }
                        $length = ([System.IO.FileInfo]$path).Length
                    }
                }
            }

            $headers = "HTTP/1.1 $status`r`nContent-Type: $contentType`r`nContent-Length: $length`r`nConnection: close`r`n`r`n"
            $headerBytes = [System.Text.Encoding]::ASCII.GetBytes($headers)
            $stream.Write($headerBytes, 0, $headerBytes.Length)
            if ($method -eq 'GET' -and $null -ne $body) {
                $stream.Write($body, 0, $body.Length)
            } elseif ($method -eq 'GET' -and $null -ne $path) {
                $stream = [System.IO.File]::OpenRead($path)
                try { $stream.CopyTo($client.GetStream()) }
                finally { $stream.Dispose() }
            }
        } catch {
            Write-Warning $_.Exception.Message
        } finally {
            $client.Close()
        }
    }
} finally {
    $listener.Stop()
}
