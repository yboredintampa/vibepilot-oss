import os, boto3
s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["STORJ_S3_ENDPOINT"],
    aws_access_key_id=os.environ["STORJ_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["STORJ_SECRET_ACCESS_KEY"],
)
s3.put_object(Bucket=os.environ.get("STORJ_BUCKET","vibepilot"),
              Key=os.environ.get("STORJ_PREFIX","") + "_health.txt",
              Body=b"ok")
print("Storj write OK")
