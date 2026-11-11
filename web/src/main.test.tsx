import { afterEach, expect, test, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App, lookup } from './main';
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
test('shows matched record from API', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ correlation_id: 'trade-1', status: 'matched', expected: { event_id: 'e1', amount_minor: 100, currency: 'USD' }, actual: { event_id: 'e2', amount_minor: 100, currency: 'USD' } }) }));
  render(<App />);
  fireEvent.change(screen.getByLabelText('Correlation ID'), { target: { value: 'trade-1' } });
  fireEvent.click(screen.getByText('Inspect'));
  await waitFor(() => expect(screen.getByText('matched')).toBeTruthy());
  expect(screen.getByText('Event ID: e2')).toBeTruthy();
});
test('reports not found', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));
  await expect(lookup('missing')).rejects.toThrow('No reconciliation found');
});
