import secrets
import hashlib
import hmac
import base64

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