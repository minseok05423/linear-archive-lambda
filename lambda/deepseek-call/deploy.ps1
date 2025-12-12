# DeepSeek Call Lambda Deployment Script
# Replace these variables with your actual values
$AWS_REGION = "ap-northeast-2"
$AWS_ACCOUNT_ID = "YOUR_AWS_ACCOUNT_ID"  # TODO: Replace with your AWS account ID
$ECR_REPO_NAME = "deepseek-call-lambda"
$IMAGE_TAG = "latest"
$LAMBDA_FUNCTION_NAME = "deepseek-call"

# Environment variables - TODO: Replace with your actual values
$SUPABASE_URL = "YOUR_SUPABASE_URL"
$SUPABASE_KEY = "YOUR_SUPABASE_KEY"
$VOYAGE_KEY = "YOUR_VOYAGE_KEY"
$DEEPSEEK_API_KEY = "YOUR_DEEPSEEK_KEY"

Write-Host "=== DeepSeek Call Lambda Deployment ===" -ForegroundColor Cyan

# Check if Docker is running
Write-Host "Checking Docker..." -ForegroundColor Yellow
try {
    docker info | Out-Null
    Write-Host "✓ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker is not running. Please start Docker Desktop first." -ForegroundColor Red
    exit 1
}

# Navigate to Lambda directory
Set-Location $PSScriptRoot
Write-Host "Working directory: $(Get-Location)" -ForegroundColor Gray

# Step 1: Create ECR repository (ignore error if exists)
Write-Host "`n[1/7] Creating ECR repository..." -ForegroundColor Yellow
aws ecr create-repository --repository-name $ECR_REPO_NAME --region $AWS_REGION 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ ECR repository created" -ForegroundColor Green
} else {
    Write-Host "ℹ ECR repository already exists (this is fine)" -ForegroundColor Gray
}

# Step 2: Authenticate Docker to ECR
Write-Host "`n[2/7] Authenticating Docker to ECR..." -ForegroundColor Yellow
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Docker authenticated to ECR" -ForegroundColor Green
} else {
    Write-Host "✗ Docker authentication failed" -ForegroundColor Red
    exit 1
}

# Step 3: Build Docker image
Write-Host "`n[3/7] Building Docker image..." -ForegroundColor Yellow
docker build --platform linux/amd64 -t $ECR_REPO_NAME .
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Docker image built successfully" -ForegroundColor Green
} else {
    Write-Host "✗ Docker build failed" -ForegroundColor Red
    exit 1
}

# Step 4: Tag the image
Write-Host "`n[4/7] Tagging Docker image..." -ForegroundColor Yellow
docker tag "${ECR_REPO_NAME}:latest" "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/${ECR_REPO_NAME}:${IMAGE_TAG}"
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Image tagged" -ForegroundColor Green
} else {
    Write-Host "✗ Image tagging failed" -ForegroundColor Red
    exit 1
}

# Step 5: Push to ECR
Write-Host "`n[5/7] Pushing image to ECR..." -ForegroundColor Yellow
docker push "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/${ECR_REPO_NAME}:${IMAGE_TAG}"
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Image pushed to ECR" -ForegroundColor Green
} else {
    Write-Host "✗ Image push failed" -ForegroundColor Red
    exit 1
}

# Step 6: Check if Lambda exists
Write-Host "`n[6/7] Checking if Lambda function exists..." -ForegroundColor Yellow
$lambdaExists = aws lambda get-function --function-name $LAMBDA_FUNCTION_NAME --region $AWS_REGION 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "ℹ Lambda function exists, updating..." -ForegroundColor Gray
    
    # Update existing Lambda
    aws lambda update-function-code `
        --function-name $LAMBDA_FUNCTION_NAME `
        --image-uri "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/${ECR_REPO_NAME}:${IMAGE_TAG}" `
        --region $AWS_REGION
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Lambda function code updated" -ForegroundColor Green
    } else {
        Write-Host "✗ Lambda update failed" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "ℹ Lambda function does not exist, creating..." -ForegroundColor Gray
    Write-Host "⚠ You need to create the Lambda function manually with proper IAM role" -ForegroundColor Yellow
    Write-Host "  Use AWS Console or run:" -ForegroundColor Gray
    Write-Host "  aws lambda create-function --function-name $LAMBDA_FUNCTION_NAME ..." -ForegroundColor Gray
    exit 1
}

# Step 7: Update environment variables
Write-Host "`n[7/7] Updating environment variables..." -ForegroundColor Yellow
aws lambda update-function-configuration `
    --function-name $LAMBDA_FUNCTION_NAME `
    --environment "Variables={SUPABASE_URL=$SUPABASE_URL,SUPABASE_KEY=$SUPABASE_KEY,VOYAGE_KEY=$VOYAGE_KEY,DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY}" `
    --region $AWS_REGION

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Environment variables updated" -ForegroundColor Green
} else {
    Write-Host "✗ Environment variable update failed" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Deployment Complete! ===" -ForegroundColor Cyan
Write-Host "Lambda function '$LAMBDA_FUNCTION_NAME' has been deployed successfully." -ForegroundColor Green
Write-Host "Image URI: $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/${ECR_REPO_NAME}:${IMAGE_TAG}" -ForegroundColor Gray
