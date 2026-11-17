import base64
import hashlib
import hmac


def verify_hmac_sha256(secret, body, signature, encoding='base64'):
    """ Whether ``signature`` is the HMAC-SHA256 of ``body`` with ``secret``.

    :param str secret: the shared secret
    :param bytes body: the raw body, exactly as received
    :param str signature: the signature sent with the body
    :param str encoding: ``base64`` or ``hex``, how the provider encodes the signature
    """
    if not secret or not signature:
        return False
    if isinstance(secret, str):
        secret = secret.encode()
    digest = hmac.new(secret, body or b'', hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode() if encoding == 'base64' else digest.hex()
    return hmac.compare_digest(expected, signature.strip())
