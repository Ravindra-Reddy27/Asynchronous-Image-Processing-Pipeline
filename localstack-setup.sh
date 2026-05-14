#!/bin/bash
echo "🚀 Initializing LocalStack AWS resources..."

# Create S3 Buckets
awslocal s3 mb s3://raw-images-local
awslocal s3 mb s3://processed-images-local

# Create Dead-Letter Queue (DLQ) First
awslocal sqs create-queue --queue-name image-processing-dlq-local

# Create Main Processing Queue and link it to the DLQ
awslocal sqs create-queue \
    --queue-name image-processing-queue-local \
    --attributes '{"RedrivePolicy": "{\"deadLetterTargetArn\":\"arn:aws:sqs:us-east-1:000000000000:image-processing-dlq-local\",\"maxReceiveCount\":\"3\"}"}'

echo "✅ Local AWS infrastructure setup complete.