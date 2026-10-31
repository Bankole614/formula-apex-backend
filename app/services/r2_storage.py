import os
import logging
from typing import Optional

# Disable AWS IMDS metadata service probe to prevent hanging in non-AWS/local/offline environments
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"

import boto3
from botocore.config import Config
from ..config import settings

logger = logging.getLogger(__name__)


class CloudflareR2Service:
    def __init__(self):
        self.bucket = settings.R2_BUCKET_NAME
        self.public_url = settings.R2_PUBLIC_URL.rstrip("/")
        self.client = None

        if settings.R2_ACCOUNT_ID and settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY:
            try:
                # Cloudflare R2 S3 endpoint format:
                # https://<ACCOUNT_ID>.r2.cloudflarestorage.com
                endpoint_url = f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
                self.client = boto3.client(
                    "s3",
                    endpoint_url=endpoint_url,
                    aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                    config=Config(
                        signature_version="s3v4",
                        connect_timeout=3,
                        read_timeout=5,
                        retries={"max_attempts": 1},
                    ),
                    region_name="auto",
                )
                logger.info("Cloudflare R2 client successfully initialized.")
            except Exception as e:
                logger.warning(f"Failed to initialize Cloudflare R2 client: {e}")
        else:
            logger.info("Cloudflare R2 credentials not set. Running in local/mock storage mode.")

    def is_configured(self) -> bool:
        return self.client is not None

    def get_public_url(self, key: str) -> str:
        """Construct the direct streaming CDN URL for an audio track or asset."""
        clean_key = key.lstrip("/")
        return f"{self.public_url}/{clean_key}"

    def generate_presigned_upload_url(
        self, key: str, content_type: str = "audio/mpeg", expires_in: int = 3600
    ) -> Optional[str]:
        """
        Generate an S3 presigned PUT URL allowing clients/admins to upload large audio files
        directly to Cloudflare R2 without routing heavy audio traffic through the backend server.
        """
        if not self.client:
            return None
        try:
            url = self.client.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in,
            )
            return url
        except Exception as e:
            logger.error(f"Error generating presigned R2 upload URL: {e}")
            return None

    def get_object(self, key: str, range_header: Optional[str] = None):
        """
        Stream an object from Cloudflare R2, supporting HTTP 206 Range requests for audio.
        """
        if not self.client:
            return None
        params = {"Bucket": self.bucket, "Key": key}
        if range_header:
            params["Range"] = range_header
        try:
            return self.client.get_object(**params)
        except Exception as e:
            logger.error(f"Error reading object from R2 ({key}): {e}")
            return None


r2_service = CloudflareR2Service()
