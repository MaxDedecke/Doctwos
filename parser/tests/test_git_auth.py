from tasks.shared import get_authenticated_url


def test_github_token_only_uses_standard_username_and_escapes_token():
    url = get_authenticated_url("https://github.com/acme/repo.git", token="ghp/a:b@c")
    assert url == "https://x-access-token:ghp%2Fa%3Ab%40c@github.com/acme/repo.git"


def test_credentials_are_escaped_and_existing_userinfo_is_replaced():
    url = get_authenticated_url(
        "https://old-user:old-token@example.com/acme/repo.git?ref=main#fragment",
        username="user@example.com",
        token="token/with:reserved@chars",
    )
    assert url == (
        "https://user%40example.com:token%2Fwith%3Areserved%40chars@example.com/"
        "acme/repo.git?ref=main#fragment"
    )


def test_non_http_git_urls_are_left_unchanged():
    url = "git@github.com:acme/repo.git"
    assert get_authenticated_url(url, username="user", token="token") == url
