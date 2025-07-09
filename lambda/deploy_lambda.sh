#!/bin/bash

# Deploy GridStatus Lambda function
# This script packages and deploys the Lambda function with the required dependencies

set -e

echo "Deploying GridStatus Lambda function..."

# Create a temporary directory for packaging
TEMP_DIR=$(mktemp -d)
echo "Using temporary directory: $TEMP_DIR"

# Copy the Lambda function
cp gridstatus_wrapper.py "$TEMP_DIR/"

# Create requirements.txt for the Lambda layer
cat > "$TEMP_DIR/requirements.txt" << EOF
gridstatus>=0.20.0
requests>=2.25.0
pandas>=1.3.0
EOF

# Install dependencies in the package directory
cd "$TEMP_DIR"
pip install -r requirements.txt -t .

# Create the deployment package
zip -r gridstatus-lambda.zip . -x "*.pyc" "__pycache__/*" "*.git*"

# Deploy to AWS Lambda (you'll need to configure this)
echo "Deployment package created: gridstatus-lambda.zip"
echo ""
echo "To deploy to AWS Lambda:"
echo "1. Create a new Lambda function"
echo "2. Upload gridstatus-lambda.zip"
echo "3. Set handler to: gridstatus_wrapper.lambda_handler"
echo "4. Set timeout to 30 seconds"
echo "5. Configure environment variables if needed"
echo ""
echo "Or use AWS CLI:"
echo "aws lambda create-function \\"
echo "  --function-name gridstatus-carbon \\"
echo "  --runtime python3.9 \\"
echo "  --handler gridstatus_wrapper.lambda_handler \\"
echo "  --zip-file fileb://gridstatus-lambda.zip \\"
echo "  --timeout 30 \\"
echo "  --memory-size 256"

# Clean up
cd -
rm -rf "$TEMP_DIR"

echo "Deployment script completed!" 