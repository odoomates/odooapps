""" Encryption of the secrets of the connectors (access tokens, client secrets…) in the database.

The key is derived from the ``om_connector_key`` option of the Odoo configuration file when it is
set, else from the secret of the database. With the option, a copy of the database alone does not
give the secrets; keep the option secret, and the same on every server of the database.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from odoo.exceptions import UserError
from odoo.tools import config

PREFIX = 'enc1:'
CONFIG_OPTION = 'om_connector_key'


def key_source(env):
    """ ``server`` when the key comes from the configuration file, else ``database``. """
    return 'server' if config.get(CONFIG_OPTION) else 'database'


def _fernet(env):
    secret = config.get(CONFIG_OPTION) or env['ir.config_parameter'].sudo().get_str('database.secret')
    if not secret:
        raise UserError(env._("No key to encrypt the secrets: set om_connector_key in the Odoo configuration."))
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b'om_connector_base',
               info=b'om-connector-secrets').derive(secret.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(env, value):
    """ The encrypted text of ``value``, or False for an empty value. """
    if not value:
        return False
    return PREFIX + _fernet(env).encrypt(value.encode()).decode()


def decrypt(env, value):
    """ The clear text of an encrypted ``value``; a value stored before the encryption is given back
    as is. """
    if not value:
        return False
    if not value.startswith(PREFIX):
        return value
    try:
        return _fernet(env).decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken as e:
        raise UserError(env._(
            "A secret of a connector cannot be decrypted: the key changed (option om_connector_key or secret of "
            "the database). Enter the credentials again.")) from e


def fingerprint(value):
    """ A short hash of a secret, to compare two of them without showing them. """
    return hashlib.sha256((value or '').encode()).hexdigest()[:12] if value else False
