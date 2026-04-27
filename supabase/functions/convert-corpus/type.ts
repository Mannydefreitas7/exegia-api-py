import type { SupabaseClient } from "@supabase/supabase-js";

interface ProcessArgs {
  jobId: string;
  tmpPath: string;
  uploadPath: string;
  metadata: CorpusMetadata;
  supabase: SupabaseClient;
}

interface CorpusMetadata {
  name: string;
  type: string;
  language: string;
  period: string;
  repository: string;
  category: string[];
  description?: string;
  licence?: string;
  credits?: string;
}

export type { CorpusMetadata, ProcessArgs };
