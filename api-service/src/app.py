import os
import uuid
import json
import boto3
from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.responses import JSONResponse
from botocore.exceptions import ClientError

app = FastAPI(title="Image Processing API")

# ---------------------------------------------------------
# AWS / LocalStack Configuration
# ---------------------------------------------------------
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
S3_BUCKET_RAW = os.getenv("S3_BUCKET_RAW", "raw-images-local")
SQS_QUEUE_NAME = os.getenv("SQS_QUEUE_NAME", "image-processing-queue-local")

# Initialize boto3 clients pointing to LocalStack
s3_client = boto3.client("s3", endpoint_url=AWS_ENDPOINT_URL, region_name=AWS_REGION)
sqs_client = boto3.client("sqs", endpoint_url=AWS_ENDPOINT_URL, region_name=AWS_REGION)

def get_queue_url():
    """Fetch the SQS Queue URL dynamically."""
    response = sqs_client.get_queue_url(QueueName=SQS_QUEUE_NAME)
    return response['QueueUrl']

# ---------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------
@app.post("/images/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_image(image: UploadFile = File(...)):
    # 1. Validate file type
    allowed_types = ["image/jpeg", "image/png"]
    if image.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid image file type. Only JPEG and PNG are allowed."
        )

    # 2. Generate Unique ID and define S3 Key
    image_id = str(uuid.uuid4())
    file_extension = image.filename.split('.')[-1]
    s3_key = f"{image_id}.{file_extension}"

    try:
        # 3. Upload raw image to S3
        s3_client.upload_fileobj(image.file, S3_BUCKET_RAW, s3_key)

        # 4. Publish message to SQS
        queue_url = get_queue_url()
        message_body = {
            "image_id": image_id,
            "s3_key_raw": s3_key
        }
        
        sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message_body)
        )

        # 5. Return immediate response to the user
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"image_id": image_id, "message": "Image upload initiated."}
        )

    except Exception as e:
        print(f"Error during upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error processing the upload."
        )

S3_BUCKET_PROCESSED = os.getenv("S3_BUCKET_PROCESSED", "processed-images-local")

@app.get("/images/processed/{image_id}", status_code=status.HTTP_200_OK)
async def get_processed_image(image_id: str):
    processed_s3_key = f"{image_id}_thumbnail.png"

    try:
        # 1. Check if the file actually exists in the processed bucket
        s3_client.head_object(Bucket=S3_BUCKET_PROCESSED, Key=processed_s3_key)

        # 2. Generate a pre-signed URL valid for 1 hour (3600 seconds)
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': S3_BUCKET_PROCESSED,
                'Key': processed_s3_key
            },
            ExpiresIn=3600
        )
        presigned_url = presigned_url.replace("http://localstack:4566", "http://localhost:4566")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "image_id": image_id,
                "status": "processed",
                "url": presigned_url
            }
        )

    except ClientError as e:
        # If head_object throws a 404, the file isn't there yet (or doesn't exist)
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "404":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Processed image not found. It may still be processing or the ID is invalid."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error checking image status."
            )