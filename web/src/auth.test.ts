import { afterEach, expect, test, vi } from 'vitest';
import { authConfig, bearerToken, finishSignIn, signOut } from './auth';

const config = { issuer: 'https://id.example', clientId: 'console', audience: 'ledger-api', redirectUri: 'https://app.example/' };
afterEach(() => {
  vi.unstubAllGlobals(); vi.unstubAllEnvs(); sessionStorage.clear(); signOut();
  history.replaceState(null, '', '/');
});
test('rejects incomplete frontend OIDC configuration', () => {
  vi.stubEnv('VITE_OIDC_ISSUER', 'https://id.example');
  expect(authConfig).toThrow('Incomplete OIDC configuration');
});
test('rejects callback with no transaction and clears code from URL', async () => {
  history.replaceState(null, '', '/?code=secret&state=x');
  await expect(finishSignIn(config)).rejects.toThrow('transaction missing');
  expect(location.search).toBe('');
});
test('rejects state mismatch before contacting token endpoint', async () => {
  sessionStorage.setItem('ledger-bridge-oidc-transaction', JSON.stringify({ state: 'one', verifier: 'test', created: Date.now() }));
  history.replaceState(null, '', '/?code=secret&state=two');
  const fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  await expect(finishSignIn(config)).rejects.toThrow('Invalid sign-in state');
  expect(fetchMock).not.toHaveBeenCalled();
});
test('exchanges code with PKCE verifier and keeps token in memory', async () => {
  sessionStorage.setItem('ledger-bridge-oidc-transaction', JSON.stringify({ state: 'one', verifier: 'verifier', created: Date.now() }));
  history.replaceState(null, '', '/?code=abc&state=one');
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ issuer: 'https://id.example', authorization_endpoint: 'https://id.example/authorize', token_endpoint: 'https://id.example/token' }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ access_token: 'short-lived', expires_in: 3600, token_type: 'Bearer' }) });
  vi.stubGlobal('fetch', fetchMock);
  expect(await finishSignIn(config)).toBe(true);
  expect(fetchMock.mock.calls[1][1].body.get('code_verifier')).toBe('verifier');
  expect(bearerToken()).toBe('short-lived');
  expect(location.search).toBe('');
  signOut();
  expect(bearerToken()).toBeNull();
});
