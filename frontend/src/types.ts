/** A single source reference returned by the RAG backend */
export interface SourceRef {
  title: string;
  content_preview?: string;
  score?: number;
  source_url?: string;
  published_at?: string;
}
