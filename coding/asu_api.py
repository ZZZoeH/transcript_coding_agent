"""Read the local credential for each authenticated request; never persist it."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

KEY_FILE = Path(__file__).resolve().parents[1] / 'create-ai_api-key.text'
ALLOWED_HOSTS = frozenset({'api-main.aiml.asu.edu', 'api-main-poc.aiml.asu.edu', 'api-main-beta.aiml.asu.edu'})


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_api_key():
    try:
        value = KEY_FILE.read_text(encoding='utf-8-sig').strip()
    except OSError:
        raise ValueError('Cannot read the local ASU key file') from None
    if value.lower().startswith('bearer '): value = value[7:].strip()
    if not value or any(c.isspace() for c in value) or not value.isascii():
        raise ValueError('ASU key file must contain only a single API key')
    return value


def request_json(endpoint, payload=None, timeout=55):
    url = urllib.parse.urlsplit(endpoint)
    if (url.scheme != 'https' or url.hostname not in ALLOWED_HOSTS
            or url.username or url.password or url.port not in (None, 443)
            or url.query or url.fragment):
        raise ValueError('Credentials may only be sent to an approved ASU API HTTPS host')
    for attempt in range(3):
        # Re-read immediately before EVERY transmission, including a retry.
        credential = read_api_key()
        request = urllib.request.Request(endpoint,
            data=None if payload is None else json.dumps(payload, allow_nan=False).encode(),
            headers={'Authorization': 'Bearer ' + credential, 'Content-Type': 'application/json'},
            method='GET' if payload is None else 'POST')
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
                # Never let an echoed credential reach a raw artifact or exception message.
                body = response.read().replace(credential.encode(), b'[REDACTED]')
            try:
                decoded = json.loads(body)
                def redact(value):
                    if isinstance(value, str): return value.replace(credential, '[REDACTED]')
                    if isinstance(value, list): return [redact(item) for item in value]
                    if isinstance(value, dict): return {redact(key):redact(item) for key,item in value.items()}
                    return value
                return redact(decoded)
            except (ValueError, UnicodeError):
                raise RuntimeError('ASU returned an invalid JSON response') from None
        except urllib.error.HTTPError as error:
            status = error.code
            error.close()
            if status in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            raise RuntimeError(f'ASU HTTP {status}; check access/model/quota') from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            raise RuntimeError('ASU network request failed or timed out') from None
