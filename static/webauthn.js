// WebAuthn helper functions for M/Monit Hub

/**
 * Convert base64url string to ArrayBuffer
 */
function base64urlToBuffer(base64url) {
  const padding = '='.repeat((4 - base64url.length % 4) % 4);
  const base64 = (base64url + padding)
    .replace(/-/g, '+')
    .replace(/_/g, '/');
  const raw = atob(base64);
  return Uint8Array.from(raw, c => c.charCodeAt(0)).buffer;
}

/**
 * Convert ArrayBuffer to base64url string
 */
function bufferToBase64url(buffer) {
  const bytes = new Uint8Array(buffer);
  let str = '';
  for (const byte of bytes) {
    str += String.fromCharCode(byte);
  }
  return btoa(str)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

/**
 * Login with passkey
 */
async function passkeyLogin(username) {
  // Get authentication options from server
  const beginResp = await fetch('/auth/passkey/login/begin', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username })
  });

  if (!beginResp.ok) {
    const err = await beginResp.json();
    throw new Error(err.error || 'Failed to start authentication');
  }

  const options = await beginResp.json();

  // Convert challenge and credential IDs from base64url
  options.challenge = base64urlToBuffer(options.challenge);
  if (options.allowCredentials) {
    options.allowCredentials = options.allowCredentials.map(cred => ({
      ...cred,
      id: base64urlToBuffer(cred.id)
    }));
  }

  // Prompt user for passkey
  let credential;
  try {
    credential = await navigator.credentials.get({ publicKey: options });
  } catch (e) {
    if (e.name === 'NotAllowedError') {
      throw new Error('Authentication cancelled');
    }
    throw new Error('Passkey authentication failed: ' + e.message);
  }

  // Prepare response for server
  const response = {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    response: {
      clientDataJSON: bufferToBase64url(credential.response.clientDataJSON),
      authenticatorData: bufferToBase64url(credential.response.authenticatorData),
      signature: bufferToBase64url(credential.response.signature),
    },
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment,
  };

  if (credential.response.userHandle) {
    response.response.userHandle = bufferToBase64url(credential.response.userHandle);
  }

  // Send to server for verification
  const completeResp = await fetch('/auth/passkey/login/complete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(response)
  });

  if (!completeResp.ok) {
    const err = await completeResp.json();
    throw new Error(err.error || 'Authentication verification failed');
  }

  return await completeResp.json();
}

/**
 * Register a new passkey
 */
async function passkeyRegister(name = 'Passkey') {
  // Get registration options from server
  const beginResp = await fetch('/auth/passkey/register/begin', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  });

  if (!beginResp.ok) {
    const err = await beginResp.json();
    throw new Error(err.error || 'Failed to start registration');
  }

  const options = await beginResp.json();

  // Convert from base64url
  options.challenge = base64urlToBuffer(options.challenge);
  options.user.id = base64urlToBuffer(options.user.id);
  if (options.excludeCredentials) {
    options.excludeCredentials = options.excludeCredentials.map(cred => ({
      ...cred,
      id: base64urlToBuffer(cred.id)
    }));
  }

  // Create credential
  let credential;
  try {
    credential = await navigator.credentials.create({ publicKey: options });
  } catch (e) {
    if (e.name === 'NotAllowedError') {
      throw new Error('Registration cancelled');
    }
    if (e.name === 'InvalidStateError') {
      throw new Error('This passkey is already registered');
    }
    throw new Error('Passkey registration failed: ' + e.message);
  }

  // Prepare response for server
  const response = {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    response: {
      clientDataJSON: bufferToBase64url(credential.response.clientDataJSON),
      attestationObject: bufferToBase64url(credential.response.attestationObject),
    },
    type: credential.type,
    name: name,
    authenticatorAttachment: credential.authenticatorAttachment,
  };

  // Send to server for verification
  const completeResp = await fetch('/auth/passkey/register/complete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(response)
  });

  if (!completeResp.ok) {
    const err = await completeResp.json();
    throw new Error(err.error || 'Registration verification failed');
  }

  return await completeResp.json();
}

/**
 * Check if WebAuthn is supported
 */
function isWebAuthnSupported() {
  return window.PublicKeyCredential !== undefined;
}
