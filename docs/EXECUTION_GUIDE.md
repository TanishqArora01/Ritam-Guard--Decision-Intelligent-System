# Execution Guide (Unified Baseline)

## 1. Main Application (Recommended)

From `fraud-detection-milestone-a`:

```powershell
Set-Location "F:/Projects/Decision Intelligent System/fraud-detection-milestone-a"
docker compose -f docker-compose.ui.yml up -d --build
```

Endpoints:
- Frontend: `http://localhost:3005/login`
- Backend health: `http://localhost:8400/health`

## 2. Full Stack (Optional)

```powershell
Set-Location "F:/Projects/Decision Intelligent System/fraud-detection-milestone-a"
docker compose -f docker-compose.yml up -d --build
```

## 3. Validation Commands

```powershell
# Compose syntax
Set-Location "F:/Projects/Decision Intelligent System/fraud-detection-milestone-a"
docker compose -f docker-compose.ui.yml config

docker compose -f docker-compose.yml config

# Runtime checks
Invoke-WebRequest -UseBasicParsing http://localhost:3005/login
Invoke-WebRequest -UseBasicParsing http://localhost:8400/health
```

## 4. Legacy Branch Policy

- Keep only one active runtime stack at a time due shared fixed container names.
- Use legacy folders (`p-*`, `changes`, `milestone-b`, `milestone-c`) for reference and extraction only.

## 5. Cleanup Recommendation

- Keep: `fraud-detection-milestone-a`
- Keep temporarily for patch harvesting: `fraud-detection changes`
- Remove duplicate patch snapshot after merge: `fraud-detection changes -2`
