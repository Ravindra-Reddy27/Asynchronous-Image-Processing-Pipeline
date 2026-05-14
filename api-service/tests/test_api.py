from fastapi.testclient import TestClient
from src.app import app

# Initialize the test client with our FastAPI app
client = TestClient(app)

def test_upload_invalid_file_type():
    """Test that the API rejects non-image files."""
    # Simulate a user uploading a simple text file
    files = {"image": ("document.txt", b"This is a text document, not an image.", "text/plain")}
    
    response = client.post("/images/upload", files=files)
    
    # We expect a 400 Bad Request
    assert response.status_code == 400
    assert "Invalid image file type" in response.json()["detail"]

def test_upload_valid_image():
    """Test that the API accepts valid images and returns a 202."""
    # Simulate a user uploading a valid JPEG (we can just pass dummy bytes for the test)
    files = {"image": ("photo.jpg", b"fake_image_bytes_here", "image/jpeg")}
    
    response = client.post("/images/upload", files=files)
    
    # We expect a 202 Accepted and a JSON response containing an image_id
    assert response.status_code == 202
    data = response.json()
    assert "image_id" in data
    assert "message" in data
    assert data["message"] == "Image upload initiated."

def test_get_nonexistent_image():
    """Test the retrieval endpoint with a fake ID."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/images/processed/{fake_id}")
    
    # We expect a 404 Not Found because this ID doesn't exist in S3
    assert response.status_code == 404