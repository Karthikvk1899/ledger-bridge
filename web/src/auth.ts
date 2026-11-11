export type AuthConfig = { issuer: string; clientId: string; audience: string; redirectUri: string; scope?: string };
type Tokens = { access_token: string; expires_in: number; token_type: string };
const transactionKey = 'ledger-bridge-oidc-transaction';
let accessToken: string | null = null;
let expiresAt = 0;

export function authConfig(): AuthConfig | null {
  const issuer = import.meta.env.VITE_OIDC_ISSUER;
  const clientId = import.meta.env.VITE_OIDC_CLIENT_ID;
  const audience = import.meta.env.VITE_OIDC_AUDIENCE;
  if (!issuer && !clientId && !audience) return null;
  if (!issuer || !clientId || !audience) throw new Error('Incomplete OIDC configuration');
  const redirectUri = import.meta.env.VITE_OIDC_REDIRECT_URI || `${location.origin}/`;
  if (!issuer.startsWith('https://') || !redirectUri.startsWith('https://')) throw new Error('OIDC requires HTTPS');
  return { issuer: issuer.replace(/\/$/, ''), clientId, audience, redirectUri, scope: import.meta.env.VITE_OIDC_SCOPE || 'openid profile' };
}

async function endpoints(config: AuthConfig): Promise<{ authorization_endpoint: string; token_endpoint: string }> {
  const res = await fetch(`${config.issuer}/.well-known/openid-configuration`);
  if (!res.ok) throw new Error('Could not load identity provider configuration');
  const data = await res.json();
  if (data.issuer !== config.issuer) throw new Error('Identity provider issuer mismatch');
  for (const key of ['authorization_endpoint', 'token_endpoint'] as const) {
    if (typeof data[key] !== 'string' || !data[key].startsWith('https://')) throw new Error('Invalid identity provider endpoint');
  }
  return data;
}

function random(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return base64url(bytes);
}
function base64url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export async function signIn(config: AuthConfig): Promise<void> {
  const { authorization_endpoint } = await endpoints(config);
  const state = random();
  const verifier = random();
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  const challenge = base64url(new Uint8Array(digest));
  sessionStorage.setItem(transactionKey, JSON.stringify({ state, verifier, created: Date.now() }));
  const url = new URL(authorization_endpoint);
  for (const [key, value] of Object.entries({ response_type: 'code', client_id: config.clientId, redirect_uri: config.redirectUri, scope: config.scope || 'openid profile', audience: config.audience, state, code_challenge: challenge, code_challenge_method: 'S256' })) url.searchParams.set(key, value);
  location.assign(url.toString());
}

export async function finishSignIn(config: AuthConfig): Promise<boolean> {
  const url = new URL(location.href);
  if (!url.searchParams.has('code') && !url.searchParams.has('error')) return false;
  const saved = sessionStorage.getItem(transactionKey);
  sessionStorage.removeItem(transactionKey);
  history.replaceState(null, '', url.pathname + url.hash);
  if (!saved) throw new Error('Sign-in transaction missing');
  const { state, verifier, created } = JSON.parse(saved);
  if (typeof state !== 'string' || typeof verifier !== 'string' || typeof created !== 'number' || Date.now() - created > 600_000 || url.searchParams.get('state') !== state) throw new Error('Invalid sign-in state');
  if (url.searchParams.has('error')) throw new Error('Sign-in was rejected');
  const code = url.searchParams.get('code');
  if (!code) throw new Error('Authorization code missing');
  const { token_endpoint } = await endpoints(config);
  const response = await fetch(token_endpoint, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ grant_type: 'authorization_code', client_id: config.clientId, code, code_verifier: verifier, redirect_uri: config.redirectUri }) });
  if (!response.ok) throw new Error('Token exchange failed');
  const tokens = await response.json() as Tokens;
  if (tokens.token_type.toLowerCase() !== 'bearer' || !tokens.access_token || !Number.isFinite(tokens.expires_in) || tokens.expires_in <= 0) throw new Error('Invalid token response');
  accessToken = tokens.access_token;
  expiresAt = Date.now() + tokens.expires_in * 1000;
  return true;
}

export function bearerToken(): string | null {
  return accessToken && Date.now() < expiresAt - 30_000 ? accessToken : null;
}
export function signOut(): void { accessToken = null; expiresAt = 0; }
