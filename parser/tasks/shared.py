def get_authenticated_url(url: str, username: str = None, token: str = None) -> str:
    """
    Constructs an authenticated URL for git cloning/crawling by inserting
    credentials into the HTTP/HTTPS scheme if a token is provided.
    """
    if not token:
        return url
    
    prefix = "https://"
    if url.startswith("https://"):
        url_stripped = url[8:]
    elif url.startswith("http://"):
        url_stripped = url[7:]
        prefix = "http://"
    else:
        url_stripped = url
        
    if username:
        auth_part = f"{username}:{token}"
    else:
        auth_part = f"{token}"
        
    return f"{prefix}{auth_part}@{url_stripped}"
