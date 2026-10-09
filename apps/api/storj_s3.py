import os
import boto3

S3_ENDPOINT = os.getenv("STORJ_S3_ENDPOINT", "https://gateway.storjshare.io")
S3_ACCESS_KEY = os.getenv("STORJ_ACCESS_KEY_ID")
S3_SECRET_KEY = os.getenv("STORJ_SECRET_ACCESS_KEY")
S3_BUCKET     = os.getenv("STORJ_BUCKET", "vibepilot")
S3_PREFIX     = os.getenv("STORJ_PREFIX", "")

_session = boto3.session.Session()
s3 = _session.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
)

def _with_prefix(key: str) -> str:
    if S3_PREFIX and not key.startswith(S3_PREFIX):
        return f"{S3_PREFIX}{key}"
    return key

def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream"):
    k = _with_prefix(key)
    s3.put_object(Bucket=S3_BUCKET, Key=k, Body=data, ContentType=content_type)
    return k
