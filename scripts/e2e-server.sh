#!/usr/bin/env bash
# سرور E2E — دیتابیس یکبارمصرف + داده اولیه + uvicorn روی 8000
# استفاده: bash scripts/e2e-server.sh   (Playwright webServer این اسکریپت را اجرا می‌کند)
set -e
cd "$(dirname "$0")/../backend"
# فعال‌سازی venv در صورت وجود
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
fi
export BPMS_DATABASE_URL="${BPMS_DATABASE_URL:-sqlite:///./data/e2e.db}"
mkdir -p data
rm -f data/e2e.db data/e2e.db-wal data/e2e.db-shm
python -m app.seed
exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
