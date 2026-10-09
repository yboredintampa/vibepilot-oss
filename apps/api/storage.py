# storage.py
import os
import boto3
from botocore.client import Config
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from dotenv import load_dotenv
import uuid

from auth import require_user
from vp_security import require_admin

load_dotenv()

router = APIRouter(prefix="/storage", tags=["storage"])


def make_s3():
    try:
        endpoint_url = os.environ["STORJ_S3_ENDPOINT"]
        ak = os.environ["STORJ_ACCESS_KEY_ID"]
        sk = os.environ["STORJ_SECRET_ACCESS_KEY"]
    except KeyError as e:
        raise HTTPException(status_code=500, detail="Storage is not configured")

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=ak,
        aws_secret_access_key=sk,
        region_name=os.getenv("STORJ_REGION", "us-east-1"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


@router.get("/debug", dependencies=[Depends(require_admin)])
def debug_env():
    return {
        "STORJ_S3_ENDPOINT": bool(os.getenv("STORJ_S3_ENDPOINT")),
        "STORJ_ACCESS_KEY_ID": "***" if os.getenv("STORJ_ACCESS_KEY_ID") else None,
        "STORJ_SECRET_ACCESS_KEY": "***" if os.getenv("STORJ_SECRET_ACCESS_KEY") else None,
        "STORJ_BUCKET": os.getenv("STORJ_BUCKET"),
        "STORJ_PREFIX": os.getenv("STORJ_PREFIX"),
    }


@router.post("/test-presigned")
def test_presigned(user=Depends(require_user)):
    """
    Sanity check write path: generates PUT URL, PUTs bytes, returns status.
    (We got 403 before we fixed credentials/ACL stuff.)
    """
    s3 = make_s3()
    bucket = os.environ["STORJ_BUCKET"]
    key = os.getenv("STORJ_PREFIX", "") + "_health.txt"

    # Generate presigned PUT
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": "text/plain"},
        ExpiresIn=60,
    )

    # PowerShell did a second POST to your own endpoint that then did the PUT using requests.
    # You'll probably move this entirely client-side (frontend will upload directly using the URL).
    import requests
    r = requests.put(url, data=b"ok", headers={"Content-Type": "text/plain"})
    return {
        "ok": (r.status_code == 200),
        "bucket": bucket,
        "key": key,
        "status": r.status_code,
    }


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user=Depends(require_user),
):
    """
    Uploads whatever file (image, etc) to Storj.
    Namespaced by tenant so different businesses don't collide.
    Returns public-ish URL (your CDN/gateway)
    """

    tenant_id = user["tenant"]
    bucket = os.environ["STORJ_BUCKET"]
    prefix = os.getenv("STORJ_PREFIX", "").rstrip("/")
    ext = os.path.splitext(file.filename)[1] or ""
    new_name = f"{tenant_id}/{uuid.uuid4()}{ext}"

    key = f"{prefix}/{new_name}" if prefix else new_name
    key = key.lstrip("/")

    data = await file.read()

    s3 = make_s3()
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ContentType=file.content_type or "application/octet-stream",
        ContentLength=len(data),
    )

    # You can build a public URL via gateway.storjshare.io/bucket/key
    public_url = f"{os.environ['STORJ_S3_ENDPOINT'].rstrip('/')}/{bucket}/{key}"

    return {
        "ok": True,
        "key": key,
        "url": public_url,
        "size": len(data),
    }
