#!/bin/bash
# Run this in Azure Cloud Shell (portal.azure.com)
# Deploys sync_employees.py as a daily Container Apps Job (06:00 Bangkok = 23:00 UTC)

ACR="cmanbudgetacr.azurecr.io"
IMAGE="$ACR/budget-sync-employees:latest"
RG="CMAN-BUDGET-MNGT-WEB-RG"
ENV="managedEnvironment-CMANBUDGETMNGTW-b33f"
JOB="cman-budget-sync-employees"

# 1. Login to ACR
az acr login --name cmanbudgetacr

# 2. Build & push image (run from repo root after git pull)
docker build -f Dockerfile.sync -t $IMAGE .
docker push $IMAGE

# 3. Create or update the Container Apps Job
az containerapp job create \
  --name $JOB \
  --resource-group $RG \
  --environment $ENV \
  --trigger-type "Schedule" \
  --cron-expression "0 23 * * *" \
  --replica-timeout 300 \
  --replica-retry-limit 1 \
  --replica-completion-count 1 \
  --parallelism 1 \
  --image $IMAGE \
  --registry-server $ACR \
  --registry-username cmanbudgetacr \
  --registry-password "$ACR_PASSWORD" \
  --cpu 0.25 \
  --memory 0.5Gi \
  --env-vars \
    DB_SERVER="cman-budget-mngt-web-sql.database.windows.net" \
    DB_NAME="budget-mngt-web-db" \
    DB_USER="budgetmngtwebadmin" \
    DB_PASSWORD="$DB_PASSWORD" \
    CPOP_HR_SYSTEM_API_URL="https://cman.ipop.iamconsulting.co.th/api/public/tenant/cman/employeedata" \
    CPOP_HR_SYSTEM_API_KEY="$CPOP_HR_SYSTEM_API_KEY"

# 4. Verify job created
az containerapp job show --name $JOB --resource-group $RG --query "{name:name, cronExpression:properties.configuration.scheduleTriggerConfig.cronExpression, state:properties.provisioningState}"

echo ""
echo "Job runs daily at 23:00 UTC = 06:00 Bangkok time"
echo "To trigger manually: az containerapp job start --name $JOB --resource-group $RG"
