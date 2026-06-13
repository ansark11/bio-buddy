export interface AuthResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  email: string;
}

export interface HealthMetric {
  id: string;
  metric_name: string;
  metric_value: number;
  unit: string;
  category: string;
  source: string;
  recorded_at: string;
  reference_range_low?: number;
  reference_range_high?: number;
  flag?: string;
  reference_range_notes?: string;
  metadata?: Record<string, unknown>;
}

export interface ChatSource {
  type: "metric" | "chunk";
  content: string;
  metadata: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: ChatSource[];
  created_at: string;
}

export interface Document {
  id: string;
  filename: string;
  file_type: string;
  source: string;
  upload_date: string;
  processed: boolean;
  processing_error?: string;
  metadata?: {
    lab_name?: string;
    test_date?: string;
    biomarker_count?: number;
    first_date?: string;
    last_date?: string;
    days?: number;
    breakdown?: Record<string, number>;
  };
}

export interface ExtractedBiomarker {
  name: string;
  standardized_name: string;
  value: number;
  unit: string;
  flag?: string;
  reference_range_low?: number;
  reference_range_high?: number;
  reference_range_notes?: string;
}

export interface BloodTestUploadResult {
  document_id: string;
  lab_name?: string;
  test_date?: string;
  biomarkers_extracted: number;
  biomarkers_stored: number;
  chunks_embedded: number;
  biomarkers: ExtractedBiomarker[];
}

export interface AppleHealthUploadResult {
  metrics_inserted: number;
  breakdown: Record<string, number>;
}

export interface NutritionUploadResult {
  document_id: string;
  days_parsed: number;
  metrics_stored: number;
  chunks_embedded: number;
  date_range: { first: string; last: string };
}

export interface CorrelateResult {
  metric_a: string;
  metric_b: string;
  correlation: number | null;
  n: number;
  data: { date: string; a_value: number; b_value: number }[];
}

export interface TimeSeriesPoint {
  date: string;
  value: number;
}

export interface ApiError {
  detail: string;
}

export interface ChatSession {
  session_id: string;
  created_at: string;
  preview: string | null;
  message_count: number;
}
