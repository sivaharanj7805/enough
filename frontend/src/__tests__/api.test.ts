import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiFetch, ApiError, apiUrl } from '@/lib/api';

// Mock global fetch
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

describe('apiFetch', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('makes GET request with correct URL', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: 'test' }),
    });

    await apiFetch('/sites');
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/v1/sites'),
      expect.any(Object)
    );
  });

  it('includes Authorization header when token provided', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });

    await apiFetch('/sites', { token: 'my-jwt-token' });

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers.Authorization).toBe('Bearer my-jwt-token');
  });

  it('includes Content-Type header', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });

    await apiFetch('/sites');

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers['Content-Type']).toBe('application/json');
  });

  it('throws ApiError on non-ok response', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 404,
      text: () => Promise.resolve('Not found'),
    });

    await expect(apiFetch('/sites/999')).rejects.toThrow(ApiError);
    await expect(apiFetch('/sites/999')).rejects.toMatchObject({
      status: 404,
    });
  });

  it('throws ApiError with 401 on unauthorized', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 401,
      text: () => Promise.resolve('Unauthorized'),
    });

    try {
      await apiFetch('/sites');
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).status).toBe(401);
    }
  });

  it('passes POST body correctly', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: '123' }),
    });

    await apiFetch('/sites', {
      method: 'POST',
      body: JSON.stringify({ name: 'My Site', domain: 'example.com' }),
    });

    const [, options] = mockFetch.mock.calls[0];
    expect(options.method).toBe('POST');
    expect(options.body).toContain('example.com');
  });
});

describe('ApiError', () => {
  it('has correct name and status', () => {
    const error = new ApiError('Not found', 404);
    expect(error.name).toBe('ApiError');
    expect(error.status).toBe(404);
    expect(error.message).toBe('Not found');
  });

  it('is an instance of Error', () => {
    const error = new ApiError('Server error', 500);
    expect(error).toBeInstanceOf(Error);
  });
});

describe('apiUrl', () => {
  it('builds full URL with v1 prefix', () => {
    const url = apiUrl('/sites');
    expect(url).toContain('/v1/sites');
  });

  it('handles paths with query params', () => {
    const url = apiUrl('/sites?limit=10');
    expect(url).toContain('/v1/sites?limit=10');
  });
});
