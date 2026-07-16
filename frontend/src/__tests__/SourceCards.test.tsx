import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import SourceCards from '../components/SourceCards';

describe('SourceCards', () => {

  it('renders nothing when sources is empty', () => {
    const { container } = render(<SourceCards sources={[]} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when sources is null or undefined', () => {
    const { container } = render(<SourceCards sources={null as unknown as []} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders source title and [Sx] tag', () => {
    render(<SourceCards sources={[{ title: '河海大学校史' }]} />);
    expect(screen.getByText('河海大学校史')).toBeDefined();
    expect(screen.getByText('S1')).toBeDefined();
  });

  it('renders relevance score as a percentage tag', () => {
    render(<SourceCards sources={[{ title: 'Doc', score: 0.856 }]} />);
    expect(screen.getByText('85.6%')).toBeDefined();
  });

  it('renders source_url as a clickable link', () => {
    render(<SourceCards sources={[{ title: 'Doc', source_url: 'https://example.com/doc' }]} />);
    const link = screen.getByText('查看来源');
    expect(link).toBeDefined();
    expect(link.closest('a')?.getAttribute('href')).toBe('https://example.com/doc');
    expect(link.closest('a')?.getAttribute('target')).toBe('_blank');
  });

  it('renders published_at date in locale format', () => {
    render(<SourceCards sources={[{ title: 'Doc', published_at: '2024-03-15' }]} />);
    // toLocaleDateString('2024-03-15') produces '2024/3/15' in en-US / zh-CN
    expect(screen.getByText('2024/3/15')).toBeDefined();
  });

  it('truncates content_preview to 360 characters', () => {
    const longText = 'A'.repeat(500);
    render(<SourceCards sources={[{ title: 'Doc', content_preview: longText }]} />);
    const expected = 'A'.repeat(360) + '...';
    expect(screen.getByText(expected)).toBeDefined();
  });

  it('does not show "查看来源" when source_url is missing', () => {
    render(<SourceCards sources={[{ title: 'Doc', content_preview: 'some content' }]} />);
    expect(screen.queryByText('查看来源')).toBeNull();
  });

  it('renders multiple sources with sequential tags', () => {
    render(<SourceCards sources={[
      { title: 'Doc A', score: 0.9 },
      { title: 'Doc B', score: 0.5 },
      { title: 'Doc C', score: 0.3 },
    ]} />);
    expect(screen.getByText('Doc A')).toBeDefined();
    expect(screen.getByText('Doc B')).toBeDefined();
    expect(screen.getByText('Doc C')).toBeDefined();
    expect(screen.getByText('S1')).toBeDefined();
    expect(screen.getByText('S2')).toBeDefined();
    expect(screen.getByText('S3')).toBeDefined();
  });

  it('renders score progress bar for each source', () => {
    const { container } = render(<SourceCards sources={[
      { title: 'Doc A', score: 0.88 },
      { title: 'Doc B', score: 0.55 },
    ]} />);
    // Ant Progress renders a div with role="progressbar"
    const progressBars = container.querySelectorAll('[role="progressbar"]');
    expect(progressBars.length).toBe(2);
  });

});
