import type { SourceRef } from '../types';

interface SourceCardsProps {
  sources: SourceRef[];
}

/** Truncate text to maxLen characters, appending "..." if truncated */
function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '...';
}

/** Map a relevance score (0-1) to the single accent scale */
function scoreTone(score: number): { color: string } {
  if (score >= 0.7) return { color: 'var(--ok)' };
  if (score >= 0.5) return { color: 'var(--warn)' };
  return { color: 'var(--ink-3)' };
}

/**
 * 引用来源做成「索引卡」：编号 + 标题 + 相关度刻度 + 原文片段。
 * 不做成一排同款圆角卡片，避免模板感。
 */
export default function SourceCards({ sources }: SourceCardsProps) {
  if (!sources || sources.length === 0) return null;

  return (
    <ol className="mt-3 border-t border-rule/70 divide-y divide-rule/70">
      {sources.map((src, i) => {
        const hasScore = typeof src.score === 'number';
        const tone = hasScore ? scoreTone(src.score as number) : null;
        const pct = hasScore ? Math.round((src.score as number) * 100) : 0;

        return (
          <li key={i} className="py-3">
            <div className="flex items-start gap-3">
              <span
                className="num shrink-0 mt-[3px] w-6 text-[11px] text-accent"
                aria-label={`来源 ${i + 1}`}
              >
                [{i + 1}]
              </span>

              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2 flex-wrap">
                  <span className="text-[13px] font-medium text-ink-1 leading-snug">
                    {src.title || '未命名文档'}
                  </span>

                  {/* 相关度：数字 + 刻度，不只靠颜色传达 */}
                  {hasScore && tone && (
                    <span className="inline-flex items-center gap-1.5 shrink-0">
                      <span className="eyebrow text-ink-3">rel</span>
                      <span
                        className="inline-block h-[3px] w-[42px] rounded-full"
                        style={{
                          background: `linear-gradient(90deg, ${tone.color} ${pct}%, var(--rule) ${pct}%)`,
                        }}
                        aria-hidden
                      />
                      <span className="num text-[10.5px] text-ink-3">{pct}%</span>
                    </span>
                  )}
                </div>

                {src.content_preview && (
                  <p className="mt-1.5 text-[12.5px] leading-[1.75] text-ink-2">
                    {truncate(src.content_preview, 240)}
                  </p>
                )}

                <div className="mt-1.5 flex items-center gap-3 text-[11.5px]">
                  {src.source_url && (
                    <a
                      href={src.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent hover:text-accent-strong underline decoration-accent/30 underline-offset-2"
                    >
                      查看原文
                    </a>
                  )}
                  {src.published_at && (
                    <span className="num text-ink-3">
                      {new Date(src.published_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
