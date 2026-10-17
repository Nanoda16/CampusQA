import { useState, useEffect, useRef } from 'react';
import { flushSync } from 'react-dom';
import { Input, Button, message, Tooltip, Tag } from 'antd';
import {
  SendOutlined,
  PlusOutlined,
  DeleteOutlined,
  LikeOutlined,
  DislikeOutlined,
  StopOutlined,
  DownOutlined,
  PaperClipOutlined,
  BulbOutlined,
} from '@ant-design/icons';
import api from '../services/api';
import SourceCards from '../components/SourceCards';
import { streamChat, type SourceItem } from '../lib/sse';

interface Message {
  id: number;
  role: 'user' | 'ai';
  content: string;
  recordId?: number;
  fromCache?: boolean;
  sources?: any[];
  feedback?: number;
  isRAG?: boolean;
}

interface Session {
  session_id: string;
  question_count: number;
  last_question: string;
  last_answer: string;
  updated_at: string;
}

const SUGGESTIONS = [
  '河海大学是哪一年创办的？',
  '图书馆的开放时间是什么时候？',
  '计算机学院的本科专业有哪些？',
];

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSession, setCurrentSession] = useState<string>('');
  const [hotQuestions, setHotQuestions] = useState<{ question: string; count: number }[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [isRagMode, setIsRagMode] = useState(true);
  const [expandedSources, setExpandedSources] = useState<Set<number>>(new Set());

  const generateSessionId = () => 'session-' + Date.now();

  useEffect(() => {
    loadSessions();
    loadHotQuestions();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadSessions = async () => {
    try {
      const res: any = await api.get('/qa/history');
      if (res.code === 200) {
        setSessions(res.data.items || []);
      }
    } catch (e) {}
  };

  const loadHotQuestions = async () => {
    try {
      const res: any = await api.get('/qa/hot?limit=6');
      if (res.code === 200) {
        setHotQuestions(res.data.questions || []);
      }
    } catch (e) {}
  };

  const loadSessionMessages = async (sessionId: string) => {
    setCurrentSession(sessionId);
    setMessages([]);
    setLoading(true);
    try {
      const res: any = await api.get(`/qa/session/${sessionId}?page_size=100`);
      if (res.code === 200) {
        const loaded: Message[] = [];
        res.data.items.forEach((item: any) => {
          loaded.push({ id: item.id * 2, role: 'user', content: item.question });
          if (item.answer) {
            loaded.push({
              id: item.id * 2 + 1,
              role: 'ai',
              content: item.answer,
              recordId: item.id,
              sources: item.sources,
              feedback: item.feedback,
            });
          }
        });
        setMessages(loaded);
      }
    } finally {
      setLoading(false);
    }
  };

  const createNewSession = () => {
    setCurrentSession(generateSessionId());
    setMessages([]);
  };

  /** Build the last N conversation turns (excluding the just-added question)
   *  to send as multi-turn context for follow-up reference resolution. */
  const buildHistory = (msgs: Message[]): { role: string; content: string }[] =>
    msgs
      .filter((m) => m.content && m.content.trim())
      .slice(-6) // last 3 Q&A pairs
      .map((m) => ({ role: m.role === 'user' ? 'user' : 'ai', content: m.content }));

  const sendMessage = async () => {
    if (!input.trim() || loading) return;
    const question = input.trim();
    setInput('');

    const sessionId = currentSession || generateSessionId();
    if (!currentSession) setCurrentSession(sessionId);

    // Snapshot prior turns BEFORE appending the new question (for history context)
    const priorHistory = buildHistory(messages);

    setMessages((prev) => [...prev, { id: Date.now(), role: 'user', content: question }]);
    setLoading(true);

    try {
      if (isRagMode) {
        // Step 1: Create qa_record to persist conversation (also handles cache)
        const askRes: any = await api.post(`/qa/ask?question=${encodeURIComponent(question)}&session_id=${sessionId}`);
        if (askRes.code === 200) {
          if (askRes.data.from_cache) {
            // Cache hit — use cached answer directly (no streaming needed)
            setMessages((prev) => [
              ...prev,
              {
                id: Date.now(),
                role: 'ai',
                content: askRes.data.answer,
                fromCache: true,
              },
            ]);
            loadSessions();
            loadHotQuestions();
          } else {
            // Cache miss — stream the answer token-by-token (typewriter)
            const recordId = askRes.data.id;
            const aiMsgId = Date.now() + 1;
            // Insert an empty AI message placeholder to fill as tokens arrive
            setMessages((prev) => [
              ...prev,
              { id: aiMsgId, role: 'ai', content: '', isRAG: true, recordId },
            ]);

            const controller = new AbortController();
            abortRef.current = controller;
            let acc = '';
            let finalSources: SourceItem[] | undefined;

            const appendToken = (content: string) => {
              acc += content;
              flushSync(() => {
                setMessages((prev) =>
                  prev.map((m) => (m.id === aiMsgId ? { ...m, content: acc } : m)),
                );
              });
            };

            try {
              await streamChat(
                '/api/ai/query/stream',
                { question, top_k: 5, history: JSON.stringify(priorHistory) },
                {
                  onChunk: appendToken,
                  onSources: (srcs) => {
                    finalSources = srcs;
                    flushSync(() => {
                      setMessages((prev) =>
                        prev.map((m) => (m.id === aiMsgId ? { ...m, sources: srcs } : m)),
                      );
                    });
                  },
                  onDone: (result) => {
                    // Prefer the accumulated stream; fall back to done payload
                    const answer = acc || result.answer || '未获取到回答';
                    const sources = finalSources ?? result.sources;
                    setMessages((prev) =>
                      prev.map((m) =>
                        m.id === aiMsgId ? { ...m, content: answer, sources } : m,
                      ),
                    );
                    // Persist the final answer to the backend record
                    api
                      .post('/qa/answer', {
                        record_id: recordId,
                        answer,
                        sources,
                        tokens_used: 0,
                        duration_ms: 0,
                      })
                      .then(() => {
                        loadSessions();
                        loadHotQuestions();
                      })
                      .catch(() => {});
                  },
                  onError: (err) => {
                    // Ignore user-initiated aborts; surface real errors
                    if (controller.signal.aborted) return;
                    setMessages((prev) =>
                      prev.map((m) =>
                        m.id === aiMsgId && !m.content
                          ? { ...m, content: `回答失败：${err.message}` }
                          : m,
                      ),
                    );
                  },
                },
                { signal: controller.signal, maxRetries: 0 },
              );
            } catch {
              /* aborted or fatal — already handled in onError */
            } finally {
              abortRef.current = null;
            }
          }
        }
      } else {
        const res: any = await api.post(`/qa/ask?question=${encodeURIComponent(question)}&session_id=${sessionId}`);
        if (res.code === 200) {
          if (res.data.from_cache) {
            setMessages((prev) => [
              ...prev,
              {
                id: res.data.id || Date.now(),
                role: 'ai',
                content: res.data.answer,
                fromCache: true,
              },
            ]);
          } else {
            // Simulate AI answer for demo (in real scenario, would call RAG engine)
            const answer = `关于"${question}"，我暂时没有找到匹配的校园资料。这是系统演示回复，实际接入 RAG 后会根据知识库生成回答。`;
            await api.post('/qa/answer', {
              record_id: res.data.id,
              answer,
              sources: [{ title: '校园知识库', url: '#' }],
              tokens_used: 120,
              duration_ms: 800,
            });
            setMessages((prev) => [
              ...prev,
              {
                id: res.data.id || Date.now(),
                role: 'ai',
                content: answer,
                recordId: res.data.id,
                sources: [{ title: '校园知识库', url: '#' }],
              },
            ]);
          }
          loadSessions();
          loadHotQuestions();
        }
      }
    } finally {
      setLoading(false);
    }
  };

  /** Abort an in-flight streaming response (P2: stop generation). */
  const stopGeneration = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
  };

  const toggleSources = (messageId: number) => {
    setExpandedSources((prev) => {
      const next = new Set(prev);
      if (next.has(messageId)) {
        next.delete(messageId);
      } else {
        next.add(messageId);
      }
      return next;
    });
  };

  const submitFeedback = async (recordId: number, feedback: number) => {
    try {
      await api.post(`/qa/feedback?record_id=${recordId}&feedback=${feedback}`);
      message.success('反馈已提交');
      setMessages((prev) =>
        prev.map((m) => (m.recordId === recordId ? { ...m, feedback } : m)),
      );
    } catch (e) {}
  };

  const deleteSession = async (sessionId: string) => {
    try {
      await api.delete(`/qa/session/${sessionId}`);
      message.success('会话已删除');
      loadSessions();
      if (sessionId === currentSession) {
        setCurrentSession('');
        setMessages([]);
      }
    } catch (e) {}
  };

  const suggestions = hotQuestions.length
    ? hotQuestions.slice(0, 3).map((q) => q.question)
    : SUGGESTIONS;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[260px_minmax(0,1fr)] gap-5 h-[calc(100dvh-136px)] min-h-[540px]">
      {/* ── 会话索引栏 ─────────────────────────────────────────── */}
      <aside className="hidden lg:flex flex-col min-w-0 surface-sub overflow-hidden">
        <div className="p-3">
          <Button
            type="primary"
            icon={<PlusOutlined />}
            block
            onClick={createNewSession}
          >
            新会话
          </Button>
        </div>

        <div className="px-4 pt-1 pb-2 flex items-center justify-between">
          <span className="eyebrow">history</span>
          <span className="num text-[10.5px] text-ink-3">{sessions.length}</span>
        </div>

        <div className="flex-1 overflow-auto px-2 pb-2">
          {sessions.length === 0 ? (
            <div className="px-3 py-6">
              <p className="text-[12.5px] text-ink-3 leading-relaxed">
                还没有历史会话。提一个问题，这里会留下记录。
              </p>
            </div>
          ) : (
            <ul className="space-y-0.5">
              {sessions.map((s) => {
                const active = s.session_id === currentSession;
                return (
                  <li key={s.session_id}>
                    <div
                      data-active={active}
                      className="row-quiet group flex items-start gap-2 pl-4 pr-1.5 py-2 cursor-pointer"
                      onClick={() => loadSessionMessages(s.session_id)}
                    >
                      <div className="min-w-0 flex-1">
                        <div
                          className={`text-[12.5px] truncate leading-snug ${
                            active ? 'text-ink-1 font-medium' : 'text-ink-2'
                          }`}
                        >
                          {s.last_question || '新会话'}
                        </div>
                        <div className="num mt-1 text-[10px] text-ink-3 truncate">
                          {s.question_count} 条
                          {(() => {
                            const d = new Date(s.updated_at);
                            return isNaN(d.getTime())
                              ? ''
                              : ' · ' +
                                  d.toLocaleDateString(undefined, {
                                    month: '2-digit',
                                    day: '2-digit',
                                  });
                          })()}
                        </div>
                      </div>
                      <Tooltip title="删除会话">
                        <button
                          aria-label="删除会话"
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteSession(s.session_id);
                          }}
                          className="grid place-items-center w-6 h-6 shrink-0 rounded-r1 text-ink-3 opacity-0 group-hover:opacity-100 hover:text-danger focus-visible:opacity-100 transition-opacity duration-150"
                        >
                          <DeleteOutlined className="text-[11px]" />
                        </button>
                      </Tooltip>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="border-t border-rule px-3 py-3">
          <div className="flex items-center gap-1.5 pb-2">
            <BulbOutlined className="text-[11px] text-accent" />
            <span className="eyebrow">frequent</span>
          </div>
          {hotQuestions.length === 0 ? (
            <p className="text-[11.5px] text-ink-3 leading-relaxed">暂无热门问题</p>
          ) : (
            <ul className="space-y-1.5">
              {hotQuestions.map((q, i) => (
                <li key={i}>
                  <button
                    onClick={() => setInput(q.question)}
                    className="w-full text-left flex items-baseline gap-2 text-[11.5px] text-ink-2 hover:text-accent transition-colors duration-150"
                  >
                    <span className="num text-[10px] text-ink-3 shrink-0 w-3">{i + 1}</span>
                    <span className="truncate">{q.question}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      {/* ── 对话主面 ───────────────────────────────────────────── */}
      <section className="surface flex flex-col min-w-0 min-h-0 overflow-hidden">
        {/* 会话头 */}
        <div className="h-12 shrink-0 px-4 md:px-5 flex items-center justify-between gap-3 border-b border-rule">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="eyebrow shrink-0">session</span>
            <span className="num text-[11px] text-ink-3 truncate">
              {currentSession ? currentSession.slice(-8) : '未开始'}
            </span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Tag
              className="!m-0"
              color={isRagMode ? 'default' : 'default'}
              style={
                isRagMode
                  ? { background: 'var(--accent-wash)', color: 'var(--accent-strong)', borderColor: '#ecd6cd' }
                  : undefined
              }
            >
              {isRagMode ? 'RAG' : '直答'}
            </Tag>
            <button
              onClick={createNewSession}
              className="lg:hidden text-[12px] text-ink-2 hover:text-accent transition-colors"
            >
              新会话
            </button>
          </div>
        </div>

        {/* 消息流 */}
        <div className="flex-1 min-h-0 overflow-auto px-4 md:px-6 py-5">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center px-2">
              <span className="grid place-items-center w-11 h-11 rounded-[12px] bg-accent-wash text-accent border border-[#ecd6cd] text-[17px] font-semibold">
                问
              </span>
              <h2 className="mt-5 text-[19px] font-semibold tracking-tight">
                想问点什么
              </h2>
              <p className="mt-2 text-[13px] text-ink-3 max-w-[380px] leading-relaxed">
                回答会引用知识库里的原文。知识库为空时先去「知识库文档」上传资料。
              </p>
              <div className="mt-6 w-full max-w-[520px] space-y-2">
                {suggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => setInput(s)}
                    className="w-full text-left px-4 py-2.5 rounded-r2 border border-rule bg-paper-1 hover:bg-paper-2 hover:border-rule-strong transition-colors duration-150 text-[13px] text-ink-2 hover:text-ink-1"
                  >
                    <span className="num text-[10px] text-ink-3 mr-2">
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              {messages.map((m) =>
                m.role === 'user' ? (
                  <div key={m.id} className="flex justify-end">
                    <div className="max-w-[78%] md:max-w-[70%]">
                      <div className="eyebrow text-right mb-1.5">you</div>
                      <div className="rounded-r3 rounded-tr-r1 bg-accent-wash text-ink-1 px-4 py-2.5 text-[13.5px] leading-[1.75] border border-[#ecd6cd]">
                        {m.content}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div key={m.id} className="flex justify-start">
                    <div className="max-w-[86%] md:max-w-[78%] w-full">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="eyebrow">assistant</span>
                        {m.isRAG && (
                          <span className="num text-[10px] text-ink-3">rag</span>
                        )}
                        {m.fromCache && (
                          <span className="num text-[10px] text-ok">cache</span>
                        )}
                      </div>

                      <div className="rounded-r3 rounded-tl-r1 bg-paper-1 border border-rule px-4 py-3 text-[13.5px] leading-[1.8] text-ink-1 whitespace-pre-wrap break-words">
                        {m.content || (
                          <span className="inline-flex items-center gap-1.5 text-ink-3">
                            <span className="w-1 h-1 rounded-full bg-ink-3 animate-pulse" />
                            <span
                              className="w-1 h-1 rounded-full bg-ink-3 animate-pulse"
                              style={{ animationDelay: '120ms' }}
                            />
                            <span
                              className="w-1 h-1 rounded-full bg-ink-3 animate-pulse"
                              style={{ animationDelay: '240ms' }}
                            />
                            <span className="ml-1 text-[12px]">检索中</span>
                          </span>
                        )}
                      </div>

                      {/* 元操作 */}
                      <div className="mt-1.5 flex items-center gap-1.5 text-ink-3">
                        {m.recordId && (
                          <>
                            <Tooltip title="回答有用">
                              <button
                                aria-label="回答有用"
                                onClick={() => submitFeedback(m.recordId!, 1)}
                                className={`grid place-items-center w-7 h-7 rounded-r1 hover:bg-paper-1 transition-colors ${
                                  m.feedback === 1 ? 'text-accent' : ''
                                }`}
                              >
                                <LikeOutlined className="text-[12px]" />
                              </button>
                            </Tooltip>
                            <Tooltip title="回答没用">
                              <button
                                aria-label="回答没用"
                                onClick={() => submitFeedback(m.recordId!, 2)}
                                className={`grid place-items-center w-7 h-7 rounded-r1 hover:bg-paper-1 transition-colors ${
                                  m.feedback === 2 ? 'text-danger' : ''
                                }`}
                              >
                                <DislikeOutlined className="text-[12px]" />
                              </button>
                            </Tooltip>
                          </>
                        )}

                        {m.sources && m.sources.length > 0 && (
                          <button
                            onClick={() => toggleSources(m.id)}
                            aria-expanded={expandedSources.has(m.id)}
                            className="ml-1 inline-flex items-center gap-1.5 h-7 px-2 rounded-r1 text-[11.5px] text-ink-2 hover:bg-paper-1 hover:text-ink-1 transition-colors"
                          >
                            <PaperClipOutlined className="text-[11px]" />
                            <span>来源</span>
                            <span className="num text-[10px] text-ink-3">
                              {m.sources.length}
                            </span>
                            <DownOutlined
                              className={`text-[9px] transition-transform duration-200 ${
                                expandedSources.has(m.id) ? 'rotate-180' : ''
                              }`}
                            />
                          </button>
                        )}
                      </div>

                      {m.sources && m.sources.length > 0 && expandedSources.has(m.id) && (
                        <div className="mt-1 pl-1">
                          <SourceCards sources={m.sources} />
                        </div>
                      )}
                    </div>
                  </div>
                ),
              )}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* 输入区 */}
        <div className="shrink-0 border-t border-rule p-3 md:p-4">
          <div className="rounded-r3 border border-rule bg-paper-2 focus-within:border-rule-strong transition-colors duration-150">
            <Input.TextArea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="输入关于河海大学的问题…"
              autoSize={{ minRows: 1, maxRows: 5 }}
              variant="borderless"
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
              className="!px-3.5 !py-3 !text-[13.5px]"
            />
            <div className="flex items-center justify-between px-2.5 pb-2.5">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setIsRagMode(!isRagMode)}
                  aria-pressed={isRagMode}
                  className={`inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full text-[11.5px] border transition-colors duration-150 ${
                    isRagMode
                      ? 'bg-accent-wash text-accent-strong border-[#ecd6cd]'
                      : 'bg-paper-1 text-ink-3 border-rule'
                  }`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      isRagMode ? 'bg-accent' : 'bg-ink-3'
                    }`}
                  />
                  检索增强
                </button>
                <span className="hidden sm:inline num text-[10px] text-ink-3">
                  Enter 发送 · Shift+Enter 换行
                </span>
              </div>

              {loading ? (
                <Button danger icon={<StopOutlined />} onClick={stopGeneration}>
                  停止
                </Button>
              ) : (
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  onClick={sendMessage}
                  disabled={!input.trim()}
                >
                  发送
                </Button>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
