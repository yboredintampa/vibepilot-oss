# storj_check.py
"""Manual connectivity check: writes a tiny health file to the configured Storj bucket."""
import os, hashlib, base64
from dotenv import load_dotenv
load_dotenv()

import boto3
from botocore.config import Config

endpoint = os.environ["STORJ_S3_ENDPOINT"]
ak = os.environ["STORJ_ACCESS_KEY_ID"]
sk = os.environ["STORJ_SECRET_ACCESS_KEY"]
bucket = os.environ["STORJ_BUCKET"]
prefix = os.getenv("STORJ_PREFIX", "")

cfg = Config(
    signature_version="s3v4",
    s3={
        "addressing_style": "path",
        # CRITICAL: force payload signing so botocore won't use chunked encoding
        "payload_signing_enabled": True,
    },
)

s3 = boto3.client(
    "s3",
    endpoint_url=endpoint,
    aws_access_key_id=ak,
    aws_secret_access_key=sk,
    region_name=os.getenv("STORJ_REGION", "us-east-1"),
    config=cfg,
)

data = b"ok"
content_length = len(data)
content_md5 = base64.b64encode(hashlib.md5(data).digest()).decode("ascii")

resp = s3.put_object(
    Bucket=bucket,
    Key=f"{prefix}_health.txt",
    Body=data,
    ContentLength=content_length,
    ContentMD5=content_md5,
)
print("put_object OK, ETag:", resp.get("ETag"))
