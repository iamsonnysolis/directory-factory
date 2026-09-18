"""Credential testing logic — extracted from the api_test_credential route.

Each function makes a trivial API call to verify the credential is valid
without performing destructive operations.
"""


def test_google_places_api_key(value: str) -> bool:
    """Test a Google Places API key via a minimal searchText call."""
    import httpx
    resp = httpx.get(
        "https://places.googleapis.com/v1/places:searchText",
        params={"text": "test"},
        headers={"X-Goog-Api-Key": value},
        timeout=10,
    )
    return resp.status_code == 200


def test_gemini_api_key(value: str) -> bool:
    """Test a Gemini API key by listing available models."""
    import google.genai as genai
    client = genai.Client(api_key=value)
    models = list(client.models.list())
    return len(models) > 0


def test_cloudflare_api_token(value: str) -> bool:
    """Test a Cloudflare API token via the token verify endpoint."""
    import httpx
    resp = httpx.get(
        "https://api.cloudflare.com/client/v4/user/tokens/verify",
        headers={"Authorization": f"Bearer {value}"},
        timeout=10,
    )
    return resp.status_code == 200


def test_github_token(value: str) -> bool:
    """Test a GitHub token by fetching the authenticated user."""
    import httpx
    resp = httpx.get(
        "https://api.github.com/user",
        headers={"Authorization": f"token {value}"},
        timeout=10,
    )
    return resp.status_code == 200


def test_credential(credential: str, value: str):
    """Test a single credential.

    Returns (ok: bool, message: str).
    """
    if credential == "GOOGLE_PLACES_API_KEY":
        ok = test_google_places_api_key(value)
        return ok, "OK" if ok else "Test failed"
    elif credential == "GEMINI_API_KEY":
        ok = test_gemini_api_key(value)
        return ok, "OK" if ok else "Test failed"
    elif credential == "CLOUDFLARE_API_TOKEN":
        ok = test_cloudflare_api_token(value)
        return ok, "OK" if ok else "Test failed"
    elif credential == "GITHUB_TOKEN":
        ok = test_github_token(value)
        return ok, "OK" if ok else "Test failed"
    else:
        return False, f"Unknown credential: {credential}"
