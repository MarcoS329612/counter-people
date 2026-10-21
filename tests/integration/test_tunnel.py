from people_counter.adapters.tunnel import PUBLIC_URL


def test_finds_the_tunnel_url_in_the_cloudflared_log():
    line = "INF |  https://maiden-reward-paperbacks-pro.trycloudflare.com                                   |"

    match = PUBLIC_URL.search(line)

    assert match and match.group() == "https://maiden-reward-paperbacks-pro.trycloudflare.com"


def test_an_error_mentioning_the_cloudflare_api_is_not_a_tunnel_url():
    line = 'failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel": connection reset by peer'

    assert PUBLIC_URL.search(line) is None
