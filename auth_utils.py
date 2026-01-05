import secrets
import hashlib
import hmac
import base64
import json
from typing import Optional, Tuple, Dict, Any

from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
    PublicKeyCredentialDescriptor,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

def hash_password(password, salt=None):
    """Hash password with salt using PBKDF2"""
    if salt is None:
        salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}${pwd_hash.hex()}"

def verify_password(password, password_hash):
    """Verify password against hash"""
    try:
        # Check for potential runtime error if hash format is invalid
        if '$' not in password_hash:
            return False
            
        salt, hash_value = password_hash.split('$')
        # Use hmac.compare_digest for constant-time comparison to prevent timing attacks
        return hmac.compare_digest(hash_password(password, salt), password_hash)
    except:
        return False

def require_auth_user(headers, config):
    """
    Check for Basic Auth header and validate credentials against config.
    Returns username string or None.
    """
    if 'users' not in config or not config['users']:
        return 'anonymous'
    
    auth_header = headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Basic '):
        return None
    
    try:
        encoded_credentials = auth_header.split(' ')[1]
        decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
        username, password = decoded_credentials.split(':', 1)
    except Exception:
        return None

    for user in config['users']:
        if user['username'] == username:
            if verify_password(password, user['password']):
                return username
    
    return None

def get_user_tenants(username, config):
    """Get list of tenants user can access"""
    if username == 'anonymous' or 'users' not in config:
        return ['*']

    for user in config['users']:
        if user['username'] == username:
            return user.get('tenants', [])

    return []


def generate_api_token():
    """Generate a new API token with mhub_ prefix"""
    return f"mhub_{secrets.token_hex(32)}"


def verify_api_token(token, config):
    """
    Verify API token and return (username, user_config) if valid.
    Returns (None, None) if invalid.
    """
    if not token or not token.startswith("mhub_"):
        return None, None

    for user in config.get("users", []):
        for api_token in user.get("api_tokens", []):
            stored_token = api_token.get("token", "")
            if hmac.compare_digest(stored_token, token):
                return user["username"], user

    return None, None


# --- WebAuthn Helpers ---

def get_webauthn_config(config: Dict[str, Any]) -> Dict[str, str]:
    """Get WebAuthn configuration with defaults"""
    webauthn_cfg = config.get("webauthn", {})
    return {
        "rp_id": webauthn_cfg.get("rp_id", "localhost"),
        "rp_name": webauthn_cfg.get("rp_name", "M/Monit Hub"),
        "origin": webauthn_cfg.get("origin", "http://localhost:8080"),
    }


def generate_passkey_registration_options(
    username: str,
    user_id: bytes,
    config: Dict[str, Any],
    existing_credentials: list = None,
) -> Tuple[str, bytes]:
    """
    Generate WebAuthn registration options.
    Returns (options_json, challenge_bytes).
    """
    webauthn_cfg = get_webauthn_config(config)
    exclude_credentials = []

    if existing_credentials:
        for cred in existing_credentials:
            exclude_credentials.append(
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(cred["id"]))
            )

    options = generate_registration_options(
        rp_id=webauthn_cfg["rp_id"],
        rp_name=webauthn_cfg["rp_name"],
        user_id=user_id,
        user_name=username,
        user_display_name=username,
        exclude_credentials=exclude_credentials,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )

    return options_to_json(options), options.challenge


def verify_passkey_registration(
    credential: Dict[str, Any],
    challenge: bytes,
    config: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Verify WebAuthn registration response.
    Returns credential data dict or None if invalid.
    """
    webauthn_cfg = get_webauthn_config(config)

    try:
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=webauthn_cfg["rp_id"],
            expected_origin=webauthn_cfg["origin"],
        )

        return {
            "id": bytes_to_base64url(verification.credential_id),
            "public_key": bytes_to_base64url(verification.credential_public_key),
            "sign_count": verification.sign_count,
        }
    except Exception:
        return None


def generate_passkey_authentication_options(
    username: str,
    config: Dict[str, Any],
    user_credentials: list = None,
) -> Tuple[str, bytes]:
    """
    Generate WebAuthn authentication options.
    Returns (options_json, challenge_bytes).
    """
    webauthn_cfg = get_webauthn_config(config)
    allow_credentials = []

    if user_credentials:
        for cred in user_credentials:
            allow_credentials.append(
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(cred["id"]))
            )

    options = generate_authentication_options(
        rp_id=webauthn_cfg["rp_id"],
        allow_credentials=allow_credentials if allow_credentials else None,
        user_verification=UserVerificationRequirement.PREFERRED,
    )

    return options_to_json(options), options.challenge


def verify_passkey_authentication(
    credential: Dict[str, Any],
    challenge: bytes,
    stored_credential: Dict[str, Any],
    config: Dict[str, Any],
) -> Optional[int]:
    """
    Verify WebAuthn authentication response.
    Returns new sign_count or None if invalid.
    """
    webauthn_cfg = get_webauthn_config(config)

    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=webauthn_cfg["rp_id"],
            expected_origin=webauthn_cfg["origin"],
            credential_public_key=base64url_to_bytes(stored_credential["public_key"]),
            credential_current_sign_count=stored_credential.get("sign_count", 0),
        )

        return verification.new_sign_count
    except Exception:
        return None


def find_user_by_passkey(credential_id: str, config: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Find user and credential by credential ID.
    Returns (username, credential_dict) or (None, None).
    """
    for user in config.get("users", []):
        for cred in user.get("passkeys", []):
            if cred["id"] == credential_id:
                return user["username"], cred
    return None, None