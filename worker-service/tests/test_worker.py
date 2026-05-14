import os
import pytest
import boto3
from moto import mock_s3
from PIL import Image

# Setup mock environment variables before importing worker
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["S3_BUCKET_RAW"] = "mock-raw"
os.environ["S3_BUCKET_PROCESSED"] = "mock-processed"

# Import the standard process_image function
from src.worker import process_image

@mock_s3
def test_process_image_success(tmp_path):
    """Test full worker logic using a mocked S3 environment."""
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="mock-raw")
    s3.create_bucket(Bucket="mock-processed")

    # Create a dummy raw image for testing
    dummy_image_path = tmp_path / "test.png"
    img = Image.new("RGB", (500, 500), color="red")
    img.save(dummy_image_path)

    # Upload dummy to mock raw bucket
    s3.upload_file(str(dummy_image_path), "mock-raw", "test-uuid.png")

    # Run the worker function
    success = process_image("test-uuid", "test-uuid.png")

    # Assertions
    assert success is True
    
    # Verify the thumbnail was created in the processed bucket
    response = s3.list_objects_v2(Bucket="mock-processed")
    assert "Contents" in response
    assert response["Contents"][0]["Key"] == "test-uuid_thumbnail.png"