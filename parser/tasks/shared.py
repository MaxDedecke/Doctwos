from urllib.parse import quote, urlsplit, urlunsplit


def get_authenticated_url(url: str, username: str = None, token: str = None) -> str:
    """
    Constructs an authenticated URL for git cloning/crawling by inserting
    credentials into the HTTP/HTTPS scheme if a token is provided.
    """
    if not token:
        return url

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return url

    # GitHub accepts x-access-token as the username for token-only HTTPS auth.
    if username:
        auth_part = f"{quote(username, safe='')}:{quote(token, safe='')}"
    elif parsed.hostname and parsed.hostname.lower() == "github.com":
        auth_part = f"x-access-token:{quote(token, safe='')}"
    else:
        # Preserve token-only behavior for generic Git servers that use the token as the user.
        auth_part = quote(token, safe="")
    host = parsed.netloc.rsplit("@", 1)[-1]
    authenticated_netloc = f"{auth_part}@{host}"
    return urlunsplit((parsed.scheme, authenticated_netloc, parsed.path, parsed.query, parsed.fragment))
