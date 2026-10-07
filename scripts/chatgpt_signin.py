from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
import stat
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx2 as httpx

AUTH_BASE = "https://auth.openai.com"
API_RESOURCE = "https://api.openai.com/v1"
AUTHORIZE_URL = AUTH_BASE + "/api/accounts/authorize"
TOKEN_URL = AUTH_BASE + "/api/accounts/oauth/token"
JWKS_URL = AUTH_BASE + "/.well-known/jwks.json"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
AGENT_NAME = "Muse Personal Agent"


class SignInError(RuntimeError):
    pass


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _pkce() -> tuple[str, str]:
    verifier = _b64url_encode(secrets.token_bytes(48))
    challenge = _b64url_encode(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def _read_json(path: Path) -> dict | None:
    try:
        if not path.exists():
            return None
        if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise SignInError("credential file permissions are too broad; require 0600")
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else None
    except SignInError:
        raise
    except (OSError, ValueError, TypeError):
        raise SignInError("existing ChatGPT credential file is invalid") from None


def _write_private(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(path.parent, 0o700)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(value)
    if os.name != "nt":
        os.chmod(temp, 0o600)
    temp.replace(path)
    if os.name != "nt":
        os.chmod(path, 0o600)


def _host_id(path: Path) -> str:
    try:
        if path.exists():
            value = path.read_text().strip()
            if value.startswith("urn:uuid:"):
                return value
            raise SignInError("saved ChatGPT host id is invalid")
    except OSError:
        raise SignInError("cannot read ChatGPT host id") from None
    value = "urn:uuid:" + str(uuid.uuid4())
    _write_private(path, value + "\n")
    return value


def _rsa_verify_rs256(signing_input: bytes, signature: bytes, jwk: dict) -> None:
    try:
        n = int.from_bytes(_b64url_decode(str(jwk["n"])), "big")
        e = int.from_bytes(_b64url_decode(str(jwk["e"])), "big")
    except (KeyError, ValueError, TypeError):
        raise SignInError("OpenAI JWKS contains an invalid RSA key") from None
    key_bytes = (n.bit_length() + 7) // 8
    if not signature or len(signature) != key_bytes:
        raise SignInError("ID token signature length is invalid")
    decoded = pow(int.from_bytes(signature, "big"), e, n).to_bytes(key_bytes, "big")
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420")
    expected_tail = digest_info + hashlib.sha256(signing_input).digest()
    padding_len = key_bytes - len(expected_tail) - 3
    if padding_len < 8:
        raise SignInError("ID token RSA key is too small")
    expected = b"\x00\x01" + (b"\xff" * padding_len) + b"\x00" + expected_tail
    if not hmac.compare_digest(decoded, expected):
        raise SignInError("ID token signature validation failed")


def _validate_id_token(token: str, *, client_id: str, nonce: str, jwks: dict) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise SignInError("ID token format is invalid")
    try:
        header = json.loads(_b64url_decode(parts[0]))
        claims = json.loads(_b64url_decode(parts[1]))
        signature = _b64url_decode(parts[2])
    except (ValueError, TypeError, json.JSONDecodeError):
        raise SignInError("ID token payload is invalid") from None
    if not isinstance(header, dict) or not isinstance(claims, dict):
        raise SignInError("ID token payload is invalid")
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise SignInError("ID token algorithm is not accepted")
    keys = jwks.get("keys") if isinstance(jwks, dict) else None
    key = next(
        (
            item
            for item in keys or []
            if isinstance(item, dict)
            and item.get("kid") == header["kid"]
            and item.get("kty") == "RSA"
        ),
        None,
    )
    if key is None:
        raise SignInError("ID token signing key was not found")
    _rsa_verify_rs256((parts[0] + "." + parts[1]).encode(), signature, key)

    now = int(time.time())
    issuer = claims.get("iss")
    audience = claims.get("aud")
    audiences = {audience} if isinstance(audience, str) else set(audience or [])
    if issuer != AUTH_BASE or client_id not in audiences:
        raise SignInError("ID token issuer or audience is invalid")
    try:
        exp = int(claims["exp"])
        nbf = int(claims.get("nbf", 0))
    except (KeyError, TypeError, ValueError):
        raise SignInError("ID token lifetime is invalid") from None
    if exp < now - 30 or nbf > now + 30:
        raise SignInError("ID token is expired or not active")
    if claims.get("nonce") != nonce:
        raise SignInError("ID token nonce validation failed")
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise SignInError("ID token subject is invalid")
    return claims


class _CallbackHandler(BaseHTTPRequestHandler):
    result: dict[str, str] | None = None

    def log_message(self, format, *args):
        # OAuth codes and query parameters must never enter terminal logs.
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/auth/callback":
            self.send_response(404)
            self.end_headers()
            return
        values = {key: items[0] for key, items in parse_qs(parsed.query).items() if items}
        type(self).result = values
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Muse ChatGPT sign-in finished. You can close this tab.")


def _fetch_json(client: httpx.Client, url: str) -> dict:
    try:
        response = client.get(url)
        response.raise_for_status()
        value = response.json()
    except Exception:
        raise SignInError("OpenAI authentication metadata request failed") from None
    if not isinstance(value, dict):
        raise SignInError("OpenAI authentication metadata is invalid")
    return value


def sign_in(credentials_path: Path, host_id_path: Path, *, new_account: bool, timeout: int) -> None:
    existing = None if new_account else _read_json(credentials_path)
    host_id = _host_id(host_id_path)
    verifier, challenge = _pkce()
    state = _b64url_encode(secrets.token_bytes(24))
    nonce = _b64url_encode(secrets.token_bytes(24))

    _CallbackHandler.result = None
    server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    server.timeout = timeout
    redirect_uri = f"http://127.0.0.1:{server.server_port}/auth/callback"

    client_id = (
        str(existing.get("client_id"))
        if existing and existing.get("client_id")
        else "dynamic_agent_client"
    )
    params = {
        "client_id": client_id,
        "ext_agent_host_id": host_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "resource": API_RESOURCE,
        "state": state,
        "nonce": nonce,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    }
    if client_id == "dynamic_agent_client":
        params["agent_name_hint"] = AGENT_NAME
    else:
        if existing and existing.get("id_token"):
            params["id_token_hint"] = str(existing["id_token"])
        if existing and existing.get("email"):
            params["login_hint"] = str(existing["email"])

    authorize_url = AUTHORIZE_URL + "?" + urlencode(params)
    if not webbrowser.open(authorize_url):
        server.server_close()
        raise SignInError("Could not open the system browser for ChatGPT sign-in")
    server.handle_request()
    server.server_close()
    callback = _CallbackHandler.result
    if not callback:
        raise SignInError("ChatGPT sign-in timed out")
    if not hmac.compare_digest(callback.get("state", ""), state):
        raise SignInError("ChatGPT sign-in state validation failed")
    if callback.get("error"):
        raise SignInError("ChatGPT sign-in was declined or failed")
    code = callback.get("code")
    if not code:
        raise SignInError("ChatGPT sign-in callback did not contain a code")

    callback_client_id = callback.get("client_id")
    if client_id == "dynamic_agent_client":
        if not callback_client_id or callback_client_id == "dynamic_agent_client":
            raise SignInError("ChatGPT client registration did not complete")
        issued_client_id = callback_client_id
    else:
        if callback_client_id and callback_client_id != client_id:
            raise SignInError("ChatGPT callback returned a different client registration")
        issued_client_id = client_id

    try:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            response = client.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": issued_client_id,
                    "code": code,
                    "code_verifier": verifier,
                    "redirect_uri": redirect_uri,
                    "resource": API_RESOURCE,
                },
            )
            if response.status_code != 200:
                raise SignInError(f"ChatGPT token exchange failed (HTTP {response.status_code})")
            tokens = response.json()
            jwks = _fetch_json(client, JWKS_URL)
    except SignInError:
        raise
    except Exception:
        raise SignInError("ChatGPT token exchange failed") from None

    if not isinstance(tokens, dict) or not isinstance(tokens.get("id_token"), str):
        raise SignInError("ChatGPT token response is invalid")
    scopes = {item for item in str(tokens.get("scope") or "").split() if item}
    if "chatgpt.tokens.use.direct" not in scopes:
        raise SignInError("ChatGPT plan usage permission was not granted")
    claims = _validate_id_token(
        tokens["id_token"],
        client_id=issued_client_id,
        nonce=nonce,
        jwks=jwks,
    )
    if existing and not new_account and existing.get("subject") != claims["sub"]:
        raise SignInError("ChatGPT account identity changed during reauthorization")

    record = {
        "email": claims.get("email"),
        "issuer": claims.get("iss"),
        "subject": claims["sub"],
        "client_id": issued_client_id,
        "ext_agent_host_id": host_id,
        "id_token": tokens["id_token"],
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "token_type": tokens.get("token_type", "Bearer"),
        "expires_in": tokens.get("expires_in", 3600),
        "earliest_refresh_at": tokens.get("earliest_refresh_at"),
        "scopes": sorted(scopes),
        "saved_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    if not record["access_token"] or not record["refresh_token"]:
        raise SignInError("ChatGPT token response did not include renewable credentials")
    _write_private(credentials_path, json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(
        "ChatGPT plan connected for Muse. Credentials were stored locally with owner-only access."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect Muse to ChatGPT plan usage")
    parser.add_argument(
        "--credentials-path",
        default="~/.config/muse/chatgpt-plan.json",
        help="private OAuth credential file",
    )
    parser.add_argument(
        "--host-id-path",
        default="~/.config/muse/chatgpt-host-id",
        help="stable local host identifier",
    )
    parser.add_argument(
        "--new-account",
        action="store_true",
        help="register a new ChatGPT account/workspace instead of reauthorizing saved credentials",
    )
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    try:
        sign_in(
            Path(args.credentials_path).expanduser(),
            Path(args.host_id_path).expanduser(),
            new_account=args.new_account,
            timeout=max(30, min(args.timeout, 900)),
        )
    except SignInError as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
