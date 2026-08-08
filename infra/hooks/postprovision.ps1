# Writes .env from the azd environment so the samples run without further setup.
$ErrorActionPreference = "Stop"

azd env get-values | Out-File -FilePath ".env" -Encoding utf8

Write-Host ""
Write-Host "Wrote .env from the azd environment." -ForegroundColor Green
Write-Host "Next:"
Write-Host "  python -m 01_retrieval.create_index"
Write-Host "  python -m 01_retrieval.index_documents"
Write-Host "  python -m 01_retrieval.compare_retrieval"
Write-Host ""
Write-Host "Role assignments can take a few minutes to propagate. A 403 on the" -ForegroundColor Yellow
Write-Host "first run usually means wait, not misconfigured." -ForegroundColor Yellow
