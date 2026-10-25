import secrets
import string

links: dict[str, str] = {}

ALPHABET = string.ascii_letters + string.digits


def generate_short_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(6))


def create_short_link(original_url: str) -> str:
    short_code = generate_short_code()

    while short_code in links:
        short_code = generate_short_code()

    links[short_code] = original_url
    return short_code
