export type PlanTier = 'free' | 'pro';
export type OAuthProvider = 'google' | 'microsoft';
export type ExtensionScope = 'refine' | 'prompts:read' | 'prompts:write' | 'usage:read';
export interface APIError { error: { code: string; message: string } }
export interface User { id: string; email: string; created_at: string }
export interface AuthResponse { user: User }
export interface Usage {
  date: string; timezone: 'UTC'; plan_tier: PlanTier;
  daily_ai_limit: number; used: number; remaining: number;
}
export interface SavedPrompt {
  id: string; title: string; content: string; tags: string[]; created_at: string;
}
export interface SavePromptInput { title: string; content: string; tags?: string[] }
export interface PromptList { prompts: SavedPrompt[]; page: number; has_more: boolean }
export interface PairingRequest {
  pairing_id: string; code: string; device_secret: string; expires_at: string;
  scopes: ExtensionScope[]; approval_url: string;
}
export interface PairingExchange {
  pairing_id: string; code: string; device_secret: string;
}
export interface ExtensionAccess {
  access_token: string; token_type: 'Bearer'; token_id: string;
  expires_at: string; scopes: ExtensionScope[];
}
export interface ExtensionDevice {
  id: string; device_name: string; scopes: ExtensionScope[]; expires_at: string; revoked: boolean;
}

export type PresetId = 'coding' | 'website_briefs' | 'business_proposals' |
  'marketing' | 'research' | 'professional_comm';
export type PromptTone = 'professional' | 'concise' | 'friendly' | 'technical' | 'persuasive';
export type CompileMode = 'Build' | 'Compact';
export type GenerationEngine = 'ai' | 'local';
export interface Preset {
  id: PresetId; name: string; role: string; version: string;
  required_fields: Record<string, string>; optional_fields: Record<string, string>;
  output_constraints: string[];
}
export interface PresetList { version: string; presets: Preset[]; tones: PromptTone[]; modes: CompileMode[] }
export interface CompileRequest {
  raw_input: string; preset: PresetId; tone?: PromptTone; mode?: CompileMode;
  fields?: Record<string, string>;
}
export interface TokenMetrics {
  raw_tokens: number; generated_tokens: number; token_difference: number;
  reduction_percent: number; is_reduction: boolean; tokenizer: string;
  tokenizer_model: string; scope: 'plain_text_only'; preset_version: string;
}
export interface GenerationResponse {
  prompt: string; missing_fields: string[]; clarification_questions: string[]; assumptions: string[];
  generation_id: string; engine: GenerationEngine; metrics: TokenMetrics;
  provider_usage: { input_tokens: number | null; output_tokens: number | null; model: string | null };
  quota_reservation: { date: string; used: number; limit: number } | null;
}
export interface MetricsGroup {
  engine: GenerationEngine; generations: number; raw_tokens: number; generated_tokens: number;
  token_difference: number; provider_input_tokens: number | null; provider_output_tokens: number | null;
}
export interface MetricsSummary { days: number; scope: 'plain_text_only'; groups: MetricsGroup[] }
