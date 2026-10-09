import os
def get_page_id_and_token():
    page_id = os.getenv("FACEBOOK_PAGE_ID") or os.getenv("META_PAGE_ID")
    token   = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or os.getenv("META_PAGE_ACCESS_TOKEN")
    return page_id, token
