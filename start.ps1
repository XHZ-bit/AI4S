$key = [Environment]::GetEnvironmentVariable("DASHSCOPE_API_KEY", "Process")
if ([string]::IsNullOrWhiteSpace($key)) {
    $key = [Environment]::GetEnvironmentVariable("DASHSCOPE_API_KEY", "User")
}
if ([string]::IsNullOrWhiteSpace($key)) {
    throw "User environment variable DASHSCOPE_API_KEY is not configured"
}

$env:DASHSCOPE_API_KEY = $key
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw "Platform startup failed; inspect Docker build/service logs." }
