/**
 * SSE (Server-Sent Events) client utilities.
 *
 * Provides:
 *  - SSEDecoder: low-level SSE protocol parser (event/data/id fields, JSON)
 *  - streamChat: high-level function to consume a streaming SSE endpoint
 *    with callbacks, AbortController support, and auto-reconnect.
 *
 * Backend SSE format (current):
 *   data: {json}\n\n
 *
 * Where the JSON shape determines the event type:
 *   {"content": "..."}            -> chunk
 *   {"data": [...]}               -> sources
 *   {"answer": "...", ...}        -> done
 *   {"message": "..."}            -> status (ignored)
 *
 * Standard SSE with event: field is also supported.
 */

/* ── Types ───────────────────────────────────────────── */

export interface SSEMessage {
  event: string;
  data: unknown;
  id?: string;
}

export interface SourceItem {
  title: string;
  content_preview: string;
  score: number;
}

export interface StreamCallbacks {
  /** Called for each content token/chunk */
  onChunk?: (content: string) => void;
  /** Called when retrieval sources arrive */
  onSources?: (sources: SourceItem[]) => void;
  /** Called when the stream completes successfully */
  onDone?: (result: { answer: string; sources: SourceItem[] }) => void;
  /** Called on fatal error (after retries exhausted) */
  onError?: (error: Error) => void;
}

export interface StreamOptions {
  /** AbortSignal for cancellation */
  signal?: AbortSignal;
  /** Max number of reconnection attempts (default 3) */
  maxRetries?: number;
  /** Called before each retry attempt */
  onRetry?: (attempt: number, error: Error) => void;
}

/* ── SSEDecoder ──────────────────────────────────────── */

/**
 * Low-level SSE text protocol decoder.
 *
 * Feed raw chunks of SSE text via `feed()` and get parsed messages back.
 * Incomplete data is buffered internally across calls.
 */
export class SSEDecoder {
  private buffer = '';
  private currentEvent = '';
  private currentData: string[] = [];
  private currentId = '';

  /**
   * Feed a chunk of SSE text. Returns zero or more complete messages.
   * Partial lines are buffered until the next call.
   */
  feed(chunk: string): SSEMessage[] {
    this.buffer += chunk;
    const messages: SSEMessage[] = [];
    const lines = this.buffer.split('\n');

    // The last element may be an incomplete line — keep in buffer
    this.buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        this.currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        this.currentData.push(line.slice(6));
      } else if (line.startsWith('id: ')) {
        this.currentId = line.slice(4).trim();
      } else if (line === '') {
        // Empty line marks end of an SSE message
        if (this.currentData.length > 0) {
          messages.push(this.buildMessage());
        }
        this.currentEvent = '';
        this.currentData = [];
        this.currentId = '';
      }
      // Lines starting with ':' are SSE comments — ignored
    }

    return messages;
  }

  /** Reset all internal state. */
  reset(): void {
    this.buffer = '';
    this.currentEvent = '';
    this.currentData = [];
    this.currentId = '';
  }

  private buildMessage(): SSEMessage {
    const raw = this.currentData.join('\n');
    let data: unknown = raw;
    try {
      data = JSON.parse(raw);
    } catch {
      // Keep as raw string if not valid JSON
    }
    return {
      event: this.currentEvent || 'message',
      data,
      id: this.currentId || undefined,
    };
  }
}

/* ── streamChat ──────────────────────────────────────── */

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isDoneEvent(msg: SSEMessage): boolean {
  if (msg.event === 'done') return true;
  const d = msg.data as Record<string, unknown>;
  return typeof d.answer === 'string';
}

/**
 * Dispatch a parsed SSE message to the appropriate callback
 * based on event type (explicit `event:` field or inferred from JSON shape).
 */
function dispatchMessage(msg: SSEMessage, cb: StreamCallbacks): void {
  const d = msg.data as Record<string, unknown>;

  // Branch 1: Standard SSE with explicit event type
  if (msg.event !== 'message') {
    switch (msg.event) {
      case 'token':
      case 'chunk':
        if (typeof d.content === 'string') cb.onChunk?.(d.content);
        return;
      case 'sources':
        if (Array.isArray(d.data)) cb.onSources?.(d.data as SourceItem[]);
        return;
      case 'done':
        cb.onDone?.({
          answer: d.answer as string,
          sources: (d.sources as SourceItem[]) ?? [],
        });
        return;
      case 'error':
        cb.onError?.(new Error((d.message as string) ?? 'SSE error'));
        return;
    }
    return;
  }

  // Branch 2: No event field — infer from JSON shape (current backend format)
  if (typeof d.content === 'string') {
    cb.onChunk?.(d.content);
  } else if (Array.isArray(d.data)) {
    cb.onSources?.(d.data as SourceItem[]);
  } else if (typeof d.answer === 'string') {
    cb.onDone?.({
      answer: d.answer,
      sources: (d.sources as SourceItem[]) ?? [],
    });
  }
  // Status messages (d.message only) are intentionally ignored
}

/**
 * Connect to an SSE endpoint, read the stream, and dispatch events to the
 * provided callbacks.
 *
 * Features:
 *  - AbortController integration for cancellation
 *  - Auto-reconnect on connection drop (configurable delay & retry count)
 *  - Automatic Authorization header injection from localStorage token
 *
 * @param url    — SSE endpoint URL
 * @param params — URL query parameters
 * @param callbacks — Event callbacks
 * @param options  — AbortSignal, retry config
 */
export async function streamChat(
  url: string,
  params: Record<string, string | number>,
  callbacks: StreamCallbacks,
  options: StreamOptions = {},
): Promise<void> {
  const maxRetries = options.maxRetries ?? 3;
  let retries = 0;

  const connect = async (): Promise<void> => {
    // Early abort check — before making the HTTP request
    if (options.signal?.aborted) {
      throw new DOMException('The operation was aborted', 'AbortError');
    }

    const qs = new URLSearchParams(
      Object.entries(params).map(([k, v]) => [k, String(v)]),
    ).toString();
    const fullUrl = `${url}?${qs}`;

    const token = localStorage.getItem('token');
    const headers: Record<string, string> = {
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };

    const response = await fetch(fullUrl, { headers, signal: options.signal });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const decoder = new SSEDecoder();
    const reader = response.body!.getReader();
    const textDecoder = new TextDecoder();
    let receivedDone = false;

    // eslint-disable-next-line no-constant-condition
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;

      // Check abort after each read
      if (options.signal?.aborted) {
        throw new DOMException('The operation was aborted', 'AbortError');
      }

      const messages = decoder.feed(textDecoder.decode(value, { stream: true }));
      for (const msg of messages) {
        dispatchMessage(msg, callbacks);
        if (isDoneEvent(msg)) receivedDone = true;
      }
    }

    // If the stream ended without a done event, the connection was lost
    if (!receivedDone) {
      throw new Error('Connection closed unexpectedly');
    }
  };

  // eslint-disable-next-line no-constant-condition
  for (;;) {
    try {
      await connect();
      return;
    } catch (err) {
      if (options.signal?.aborted) throw err;
      if (retries >= maxRetries) {
        const error = err instanceof Error ? err : new Error(String(err));
        callbacks.onError?.(error);
        throw error;
      }
      retries++;
      options.onRetry?.(retries, err as Error);
      await sleep(5000);
    }
  }
}
