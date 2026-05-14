import os
import json
import time
import logging
import boto3
from botocore.exceptions import ClientError
from PIL import Image, ImageDraw

# ---------------------------------------------------------
# Structured JSON Logging Setup
# ---------------------------------------------------------
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {"level": record.levelname, "message": record.getMessage()}
        if record.exc_info:
            log_record["error"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

logger = logging.getLogger("Worker")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)

# ---------------------------------------------------------
# Configuration & Setup
# ---------------------------------------------------------
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
S3_BUCKET_RAW = os.getenv("S3_BUCKET_RAW", "raw-images-local")
S3_BUCKET_PROCESSED = os.getenv("S3_BUCKET_PROCESSED", "processed-images-local")
SQS_QUEUE_NAME = os.getenv("SQS_QUEUE_NAME", "image-processing-queue-local")

s3_client = boto3.client("s3", endpoint_url=AWS_ENDPOINT_URL, region_name=AWS_REGION)
sqs_client = boto3.client("sqs", endpoint_url=AWS_ENDPOINT_URL, region_name=AWS_REGION)

def get_queue_url():
    """Fetch the SQS Queue URL dynamically."""
    response = sqs_client.get_queue_url(QueueName=SQS_QUEUE_NAME)
    return response['QueueUrl']

# ---------------------------------------------------------
# Image Processing Logic
# ---------------------------------------------------------
def process_image(image_id, s3_key_raw):
    """Processes the image with Exponential Backoff for AWS operations."""
    local_raw_path = f"/tmp/{s3_key_raw}"
    local_processed_path = f"/tmp/{image_id}_thumbnail.png"
    processed_s3_key = f"{image_id}_thumbnail.png"

    max_retries = 3
    base_delay = 2 

    for attempt in range(max_retries):
        try:
            # 1. Download
            s3_client.download_file(S3_BUCKET_RAW, s3_key_raw, local_raw_path)

            # 2. Resize & Watermark
            with Image.open(local_raw_path) as img:
                img.thumbnail((150, 150))
                draw = ImageDraw.Draw(img)
                text = "PropelHQ"
                draw.text((img.width - draw.textlength(text) - 5, img.height - 15), text, fill="white")
                img.save(local_processed_path, format="PNG")

            # 3. Upload
            s3_client.upload_file(local_processed_path, S3_BUCKET_PROCESSED, processed_s3_key)
            
            logger.info(f"Successfully processed and uploaded: {processed_s3_key}")
            return True

        except ClientError as e:
            delay = base_delay * (2 ** attempt)
            logger.warning(f"AWS transient error processing {image_id}. Retrying in {delay}s...")
            time.sleep(delay)
        except Exception as e:
            logger.error(f"Fatal error processing {image_id}: {str(e)}")
            return False
        finally:
            if os.path.exists(local_raw_path): os.remove(local_raw_path)
            if os.path.exists(local_processed_path): os.remove(local_processed_path)
            
    logger.error(f"Failed to process {image_id} after {max_retries} attempts.")
    return False

# ---------------------------------------------------------
# Worker Polling Loop
# ---------------------------------------------------------
def poll_queue():
    # Wait briefly to ensure LocalStack is fully up before polling
    time.sleep(5)
    queue_url = get_queue_url()
    logger.info(f"Worker started. Listening to queue: {SQS_QUEUE_NAME}...")
    
    while True:
        try:
            # Receive message with Long Polling (5 seconds)
            response = sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=5 
            )

            if 'Messages' in response:
                for msg in response['Messages']:
                    receipt_handle = msg['ReceiptHandle']
                    body = json.loads(msg['Body'])
                    
                    image_id = body.get('image_id')
                    s3_key_raw = body.get('s3_key_raw')

                    logger.info(f"Received task for image: {image_id}")
                    
                    # Process the image
                    success = process_image(image_id, s3_key_raw)
                    
                    # ONLY delete the message if processing was completely successful
                    if success:
                        sqs_client.delete_message(
                            QueueUrl=queue_url,
                            ReceiptHandle=receipt_handle
                        )
                        logger.info(f"Deleted message for {image_id} from queue.")
            else:
                # No messages, sleep briefly
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Queue polling error: {e}")
            time.sleep(5) # Backoff on error

if __name__ == "__main__":
    poll_queue()