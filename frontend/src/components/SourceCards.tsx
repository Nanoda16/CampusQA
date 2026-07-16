import { Collapse, Progress, Tag } from 'antd';
import type { SourceRef } from '../types';

interface SourceCardsProps {
  sources: SourceRef[];
}

/** Truncate text to maxLen characters, appending "..." if truncated */
function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '...';
}

/** Map a relevance score (0–1) to a semantic color */
function getScoreColor(score: number): string {
  if (score > 0.7) return '#52c41a';
  if (score > 0.5) return '#faad14';
  return '#d9d9d9';
}

function getScoreTagColor(score: number): 'success' | 'warning' | 'default' {
  if (score > 0.7) return 'success';
  if (score > 0.5) return 'warning';
  return 'default';
}

export default function SourceCards({ sources }: SourceCardsProps) {
  if (!sources || sources.length === 0) return null;

  const allKeys = sources.map((_, i) => String(i));

  const items = sources.map((src, i) => ({
    key: String(i),
    label: (
      <div className="flex items-center gap-2" data-testid={`source-header-${i}`}>
        <Tag color="blue" className="text-xs">S{i + 1}</Tag>
        <span className="text-sm font-medium truncate flex-1">{src.title}</span>
        {src.score !== undefined && (
          <Progress
            percent={Math.round(src.score * 100)}
            size="small"
            type="line"
            showInfo={false}
            style={{ width: 80, flexShrink: 0 }}
            strokeColor={getScoreColor(src.score)}
          />
        )}
      </div>
    ),
    children: (
      <div data-testid={`source-body-${i}`}>
        {src.content_preview && (
          <p className="text-xs text-gray-600 mb-2 leading-relaxed">
            {truncate(src.content_preview, 360)}
          </p>
        )}
        <div className="flex items-center gap-3 text-xs text-gray-400">
          {src.source_url && (
            <a
              href={src.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:underline"
            >
              查看来源
            </a>
          )}
          {src.published_at && (
            <span>{new Date(src.published_at).toLocaleDateString()}</span>
          )}
        </div>
        {src.score !== undefined && (
          <Tag color={getScoreTagColor(src.score)} className="mt-2 text-xs">
            {(src.score * 100).toFixed(1)}%
          </Tag>
        )}
      </div>
    ),
  }));

  return (
    <Collapse
      items={items}
      defaultActiveKey={allKeys}
      ghost
      size="small"
      className="mt-2"
    />
  );
}
