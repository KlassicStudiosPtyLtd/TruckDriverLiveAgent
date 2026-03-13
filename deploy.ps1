$ErrorActionPreference = "Stop"

$PROJECT_ID = if ($env:GCP_PROJECT_ID) { $env:GCP_PROJECT_ID } else { "gen-lang-client-0509400715" }
$SERVICE_NAME = "betty"
$REGION = if ($env:GCP_REGION) { $env:GCP_REGION } else { "us-central1" }

if (-not $env:GEMINI_API_KEY) {
    Write-Error "GEMINI_API_KEY environment variable is not set. Run: `$env:GEMINI_API_KEY = 'your-key'"
    exit 1
}

Write-Host "Deploying Betty to Cloud Run..."
Write-Host "  Project: $PROJECT_ID"
Write-Host "  Region:  $REGION"
Write-Host "  Service: $SERVICE_NAME"

gcloud run deploy $SERVICE_NAME `
  --source . `
  --project $PROJECT_ID `
  --region $REGION `
  --allow-unauthenticated `
  --set-env-vars "GEMINI_API_KEY=$env:GEMINI_API_KEY,BETTY_MEMORY_KEY=betty-memory-secret-key-2026-hackathon" `
  --timeout 600 `
  --memory 512Mi `
  --cpu 1 `
  --min-instances 0 `
  --max-instances 3 `
  --session-affinity

Write-Host ""
Write-Host "Deployed! Get URL with:"
Write-Host "  gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)'"
