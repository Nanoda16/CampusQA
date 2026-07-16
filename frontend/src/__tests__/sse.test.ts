import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SSEDecoder, streamChat } from '../lib/sse';
import type { StreamCallbacks, SourceItem } from '../lib/sse';

/* ── Helpers ─────────────────────────────────────────── */

/** Build a ReadableStream from an array of SSE text chunks. */
function sseStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) {
        controller.enqueue(encoder.encode(c));
      }
      controller.close();
    },
  });
}

/** Create a mock Response for SSE endpoint. */
function mockSSEResponse(events: string[]): Response {
  return new Response(sseStream(events), {
    status: 200,
    statusText: 'OK',
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

/** Build SSE text for a data-only event (current backend format). */
function dataEvent(json: Record<string, unknown>): string {
  return `data: ${JSON.stringify(json)}\n\n`;
}

/** Build SSE text for an event with explicit event type. */
function typedEvent(event: string, data: Record<string, unknown>): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/* ── SSEDecoder ──────────────────────────────────────── */

describe('SSEDecoder', () => {
  let decoder: SSEDecoder;

  beforeEach(() => {
    decoder = new SSEDecoder();
  });

  it('parses a single data event with raw string', () => {
    const msgs = decoder.feed('data: hello world\n\n');
    expect(msgs).toHaveLength(1);
    expect(msgs[0].event).toBe('message');
    expect(msgs[0].data).toBe('hello world');
    expect(msgs[0].id).toBeUndefined();
  });

  it('parses JSON data', () => {
    const msgs = decoder.feed('data: {"content":"hello"}\n\n');
    expect(msgs).toHaveLength(1);
    expect(msgs[0].data).toEqual({ content: 'hello' });
  });

  it('parses event and data fields together', () => {
    const msgs = decoder.feed('event: token\ndata: {"content":"hello"}\n\n');
    expect(msgs).toHaveLength(1);
    expect(msgs[0].event).toBe('token');
    expect(msgs[0].data).toEqual({ content: 'hello' });
  });

  it('parses id field', () => {
    const msgs = decoder.feed('id: 42\ndata: {"x":1}\n\n');
    expect(msgs[0].id).toBe('42');
  });

  it('parses multiple events from a single chunk', () => {
    // Must end with \n\n to properly terminate the last event
    const text = 'event: token\ndata: {"content":"a"}\n\nevent: done\ndata: {"answer":"a"}\n\n';
    const msgs = decoder.feed(text);
    expect(msgs).toHaveLength(2);
    expect(msgs[0].event).toBe('token');
    expect(msgs[0].data).toEqual({ content: 'a' });
    expect(msgs[1].event).toBe('done');
    expect(msgs[1].data).toEqual({ answer: 'a' });
  });

  it('handles streaming — partial chunk across feed calls', () => {
    const m1 = decoder.feed('data: {"conte');
    expect(m1).toHaveLength(0);

    const m2 = decoder.feed('nt":"hello"}\n\n');
    expect(m2).toHaveLength(1);
    expect(m2[0].data).toEqual({ content: 'hello' });
  });

  it('ignores SSE comment lines', () => {
    const msgs = decoder.feed(': this is a comment\ndata: real\n\n');
    expect(msgs).toHaveLength(1);
    expect(msgs[0].data).toBe('real');
  });

  it('ignores extra fields like retry', () => {
    const msgs = decoder.feed('retry: 5000\ndata: ok\n\n');
    expect(msgs).toHaveLength(1);
    expect(msgs[0].data).toBe('ok');
  });

  it('returns empty array for chunk with no data line', () => {
    const msgs = decoder.feed('event: ping\n\n');
    expect(msgs).toHaveLength(0);
  });

  it('resets internal state', () => {
    decoder.feed('data: first\n\n');
    decoder.reset();
    const msgs = decoder.feed('data: second\n\n');
    expect(msgs).toHaveLength(1);
    expect(msgs[0].data).toBe('second');
  });

  it('handles trailing newline gracefully', () => {
    // Extra \n after delimiter should not create extra messages
    const msgs = decoder.feed('data: {"x":1}\n\n\n');
    expect(msgs).toHaveLength(1);
  });

  it('preserves raw string when JSON parse fails', () => {
    const msgs = decoder.feed('data: not-json\n\n');
    expect(msgs[0].data).toBe('not-json');
  });

  it('handles multi-line data (multiple data: fields)', () => {
    const msgs = decoder.feed('data: line1\ndata: line2\n\n');
    expect(msgs[0].data).toBe('line1\nline2');
  });

  it('handles event field without data field', () => {
    // Should not produce a message if there's no data line
    const msgs = decoder.feed('event: empty\n\n');
    expect(msgs).toHaveLength(0);
  });
});

/* ── streamChat ──────────────────────────────────────── */

describe('streamChat', () => {
  let callbacks: StreamCallbacks;
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    callbacks = {
      onChunk: vi.fn(),
      onSources: vi.fn(),
      onDone: vi.fn(),
      onError: vi.fn(),
    };
    fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('calls onChunk for each content event (current backend format)', async () => {
    fetchSpy.mockResolvedValue(
      mockSSEResponse([
        dataEvent({ content: 'Hello' }),
        dataEvent({ content: ' ' }),
        dataEvent({ content: 'World' }),
        dataEvent({ answer: 'Hello World', sources: [] }),
      ]),
    );

    await streamChat('/test', { q: 'hello' }, callbacks);

    expect(callbacks.onChunk).toHaveBeenCalledTimes(3);
    expect(callbacks.onChunk).toHaveBeenNthCalledWith(1, 'Hello');
    expect(callbacks.onChunk).toHaveBeenNthCalledWith(2, ' ');
    expect(callbacks.onChunk).toHaveBeenNthCalledWith(3, 'World');
  });

  it('calls onSources when sources event arrives', async () => {
    const sources: SourceItem[] = [
      { title: 'Doc 1', content_preview: 'Preview 1', score: 0.95 },
      { title: 'Doc 2', content_preview: 'Preview 2', score: 0.82 },
    ];

    fetchSpy.mockResolvedValue(
      mockSSEResponse([
        dataEvent({ data: sources }),
        dataEvent({ answer: 'Answer text', sources }),
      ]),
    );

    await streamChat('/test', { q: 'hello' }, callbacks);

    expect(callbacks.onSources).toHaveBeenCalledOnce();
    expect(callbacks.onSources).toHaveBeenCalledWith(sources);
  });

  it('calls onDone with the final answer and sources', async () => {
    const sources: SourceItem[] = [
      { title: 'Doc', content_preview: 'Preview', score: 0.9 },
    ];

    fetchSpy.mockResolvedValue(
      mockSSEResponse([
        dataEvent({ content: 'Final' }),
        dataEvent({ answer: 'Final', sources }),
      ]),
    );

    const donePromise = new Promise<{ answer: string; sources: SourceItem[] }>((resolve) => {
      callbacks.onDone = resolve;
    });

    await streamChat('/test', { q: 'hello' }, callbacks);

    const result = await donePromise;
    expect(result.answer).toBe('Final');
    expect(result.sources).toEqual(sources);
  });

  it('handles standard SSE with explicit event: field', async () => {
    fetchSpy.mockResolvedValue(
      mockSSEResponse([
        typedEvent('chunk', { content: 'Hello' }),
        typedEvent('sources', { data: [{ title: 'S1', content_preview: 'P', score: 0.5 }] }),
        typedEvent('done', { answer: 'Hello', sources: [] }),
      ]),
    );

    await streamChat('/test', { q: 'hello' }, callbacks);

    expect(callbacks.onChunk).toHaveBeenCalledWith('Hello');
    expect(callbacks.onSources).toHaveBeenCalledOnce();
    expect(callbacks.onDone).toHaveBeenCalledOnce();
  });

  it('ignores status events (message-only JSON)', async () => {
    fetchSpy.mockResolvedValue(
      mockSSEResponse([
        dataEvent({ message: '检索中...' }),
        dataEvent({ content: 'Result' }),
        dataEvent({ answer: 'Result', sources: [] }),
      ]),
    );

    await streamChat('/test', { q: 'hello' }, callbacks);

    expect(callbacks.onChunk).toHaveBeenCalledOnce();
    expect(callbacks.onDone).toHaveBeenCalledOnce();
    expect(callbacks.onError).not.toHaveBeenCalled();
  });

  it('aborts immediately when signal is already aborted', async () => {
    const controller = new AbortController();
    controller.abort();

    // spy should NOT be called because streamChat checks signal before fetch
    await expect(
      streamChat('/test', { q: 'hello' }, callbacks, { signal: controller.signal }),
    ).rejects.toThrow();

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('aborts during fetch call with pre-aborted signal', async () => {
    // Signal aborted before fetch resolves — fetch itself throws
    const controller = new AbortController();

    fetchSpy.mockImplementation((_url: string, init?: RequestInit) => {
      // Simulate fetch abort — when signal is already aborted, fetch throws
      if (init?.signal?.aborted) {
        return Promise.reject(new DOMException('The operation was aborted', 'AbortError'));
      }
      return Promise.resolve(mockSSEResponse([dataEvent({ answer: 'OK', sources: [] })]));
    });

    controller.abort();

    await expect(
      streamChat('/test', { q: 'hello' }, callbacks, { signal: controller.signal }),
    ).rejects.toThrow();
  });

  it('uses Authorization header when token is in localStorage', async () => {
    localStorage.setItem('token', 'test-token-123');
    fetchSpy.mockResolvedValue(
      mockSSEResponse([dataEvent({ answer: 'OK', sources: [] })]),
    );

    await streamChat('/test', { q: 'hello' }, callbacks);

    expect(fetchSpy).toHaveBeenCalledOnce();
    const [calledUrl, calledInit] = fetchSpy.mock.calls[0];
    expect(calledUrl).toContain('/test?q=hello');
    expect(calledInit.headers.Authorization).toBe('Bearer test-token-123');
  });

  it('retries when fetch fails (network error)', async () => {
    vi.useFakeTimers();

    let callCount = 0;
    fetchSpy.mockImplementation(() => {
      callCount++;
      if (callCount === 1) {
        return Promise.reject(new Error('Network error'));
      }
      return Promise.resolve(
        mockSSEResponse([dataEvent({ answer: 'OK', sources: [] })]),
      );
    });

    const promise = streamChat('/test', { q: 'hello' }, callbacks, { maxRetries: 3 });

    // Advance past the 5s retry delay
    await vi.advanceTimersByTimeAsync(5000);
    await promise;

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(callbacks.onDone).toHaveBeenCalledOnce();
  });

  it('exhausts retries and throws when fetch always fails', async () => {
    vi.useFakeTimers();

    fetchSpy.mockImplementation(() => Promise.reject(new Error('Network error')));

    streamChat('/test', { q: 'hello' }, callbacks, { maxRetries: 2 }).catch(() => {
      // Swallow expected rejection
    });

    // Advance past retry 1
    await vi.advanceTimersByTimeAsync(5000);
    // Advance past retry 2
    await vi.advanceTimersByTimeAsync(5000);

    // Let microtasks flush
    await vi.waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(3); // initial + 2 retries
    });
  });

  it('calls onRetry callback before each retry', async () => {
    vi.useFakeTimers();

    const onRetry = vi.fn();
    fetchSpy.mockImplementation(() => Promise.reject(new Error('Fail')));

    streamChat('/test', { q: 'hello' }, callbacks, {
      maxRetries: 2,
      onRetry,
    }).catch(() => {});

    await vi.advanceTimersByTimeAsync(5000);
    await vi.advanceTimersByTimeAsync(5000);

    await vi.waitFor(() => {
      expect(onRetry).toHaveBeenCalledTimes(2);
      expect(onRetry).toHaveBeenNthCalledWith(1, 1, expect.any(Error));
      expect(onRetry).toHaveBeenNthCalledWith(2, 2, expect.any(Error));
    });
  });

  it('retries when connection drops before done event', async () => {
    vi.useFakeTimers();

    let callCount = 0;
    fetchSpy.mockImplementation(() => {
      callCount++;
      if (callCount === 1) {
        // First connection: send one chunk then close prematurely
        const encoder = new TextEncoder();
        const stream = new ReadableStream({
          start(controller) {
            controller.enqueue(encoder.encode(dataEvent({ content: 'partial' })));
            controller.close();
          },
        });
        return Promise.resolve(
          new Response(stream, {
            status: 200,
            headers: { 'Content-Type': 'text/event-stream' },
          }),
        );
      }
      // Second connection succeeds
      return Promise.resolve(
        mockSSEResponse([dataEvent({ answer: 'full result', sources: [] })]),
      );
    });

    const promise = streamChat('/test', { q: 'hello' }, callbacks, { maxRetries: 2 });

    await vi.advanceTimersByTimeAsync(5000);
    await promise;

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(callbacks.onChunk).toHaveBeenCalledWith('partial');
    expect(callbacks.onDone).toHaveBeenCalledOnce();
  });

  it('calls onError after all retries exhausted', async () => {
    vi.useFakeTimers();

    fetchSpy.mockImplementation(() => Promise.reject(new Error('All failed')));

    streamChat('/test', { q: 'hello' }, callbacks, { maxRetries: 1 }).catch(() => {
      // Swallow expected rejection
    });

    await vi.advanceTimersByTimeAsync(5000);

    await vi.waitFor(() => {
      expect(callbacks.onError).toHaveBeenCalledOnce();
      expect(callbacks.onError).toHaveBeenCalledWith(expect.any(Error));
    });
  });
});
