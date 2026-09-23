import { useAuthStore } from '@/stores/auth'

// =============================================================================
// HTTP istemcisi
// =============================================================================

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api/v1'

/** Backend'in döndürdüğü hata (HTTP durumu + okunabilir mesaj). */
export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

type QueryValue = string | number | boolean | null | undefined
type Query = Record<string, QueryValue>

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  query?: object
  body?: unknown
  /** JSON dışı gövde (ör. ham CSV metni) */
  rawBody?: { content: string; contentType: string }
  /** false ise Authorization başlığı eklenmez ve 401'de yenileme denenmez */
  auth?: boolean
  responseType?: 'json' | 'blob'
}

function buildUrl(path: string, query?: object): string {
  const url = `${API_BASE}${path}`
  if (!query) return url
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query as Query)) {
    if (value !== undefined && value !== null && value !== '') {
      params.append(key, String(value))
    }
  }
  const qs = params.toString()
  return qs ? `${url}?${qs}` : url
}

/** FastAPI `detail` alanını (metin veya doğrulama listesi) tek bir mesaja çevirir. */
function extractErrorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : ''))
        .filter(Boolean)
        .join('; ') || fallback
    }
  }
  return fallback
}

// Aynı anda birden fazla 401 gelirse tek bir yenileme isteği yapılır.
let refreshPromise: Promise<boolean> | null = null

async function refreshAccessToken(): Promise<boolean> {
  const { refreshToken, setTokens } = useAuthStore.getState()
  if (!refreshToken) return false

  try {
    const response = await fetch(buildUrl('/auth/refresh'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (!response.ok) return false
    const data = (await response.json()) as LoginResponse
    setTokens(data.access_token, data.refresh_token)
    return true
  } catch {
    return false
  }
}

function handleSessionExpired() {
  useAuthStore.getState().logout()
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', query, body, rawBody, auth = true, responseType = 'json' } = options

  const send = () => {
    const headers: Record<string, string> = {}
    if (rawBody) {
      headers['Content-Type'] = rawBody.contentType
    } else if (body !== undefined) {
      headers['Content-Type'] = 'application/json'
    }
    const token = useAuthStore.getState().accessToken
    if (auth && token) headers['Authorization'] = `Bearer ${token}`

    return fetch(buildUrl(path, query), {
      method,
      headers,
      body: rawBody ? rawBody.content : body !== undefined ? JSON.stringify(body) : undefined,
    })
  }

  let response = await send()

  if (response.status === 401 && auth) {
    refreshPromise ??= refreshAccessToken().finally(() => {
      refreshPromise = null
    })
    if (await refreshPromise) {
      response = await send()
    } else {
      handleSessionExpired()
    }
  }

  if (!response.ok) {
    let payload: unknown = null
    try {
      payload = await response.json()
    } catch {
      // Gövde JSON değilse varsayılan mesaj kullanılır
    }
    throw new ApiError(
      extractErrorMessage(payload, `İstek başarısız oldu (${response.status})`),
      response.status
    )
  }

  if (response.status === 204) return undefined as T
  if (responseType === 'blob') return (await response.blob()) as T

  const text = await response.text()
  return (text ? JSON.parse(text) : undefined) as T
}

/** Bir Blob'u tarayıcıda dosya olarak indirtir. */
export function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

// =============================================================================
// Tipler — backend OpenAPI şemasından (/api/openapi.json) türetilmiştir
// =============================================================================

// ---- Auth / Kullanıcı ------------------------------------------------------

export interface AuthUser {
  id: string
  email: string
  name: string
  role: 'admin' | 'manager' | 'user'
  mfa_enabled: boolean
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type?: string
  expires_in: number
  user: AuthUser
}

export interface RegisterRequest {
  email: string
  password: string
  name: string
  organization_name?: string | null
}

export interface RegisterResponse {
  message: string
  user_id: string
}

export interface UpdateProfileRequest {
  name?: string | null
}

export interface UserProfile {
  id: string
  email: string
  name: string
  role: string
  organization_id: string
  organization_name: string
  mfa_enabled: boolean
  created_at: string
}

// ---- Bağlantılar (reklam hesapları) ----------------------------------------

export type SyncStatus = 'pending' | 'syncing' | 'success' | 'error' | 'auth_error'

export interface AdAccountResponse {
  id: string
  platform: string
  platform_account_id: string
  platform_account_name: string | null
  is_active: boolean
  sync_status: SyncStatus
  last_sync_at: string | null
  connected_at: string
  needs_reauth: boolean
}

export interface AdAccountListResponse {
  accounts: AdAccountResponse[]
  total: number
}

export interface ConnectResponse {
  authorization_url: string
  state: string
}

export interface PlatformAccountOption {
  account_id: string
  account_name: string
  already_connected: boolean
}

export interface AvailableAccountsResponse {
  platform: string
  accounts: PlatformAccountOption[]
}

// ---- Kampanyalar -----------------------------------------------------------

export interface AdCopyCreate {
  headline_1: string
  headline_2?: string | null
  headline_3?: string | null
  description_1: string
  description_2?: string | null
  path_1?: string | null
  path_2?: string | null
  final_url: string
  call_to_action?: string | null
  variation_name?: string | null
  is_primary?: boolean
}

export interface AdCopyResponse {
  id: string
  headline_1: string
  headline_2: string | null
  headline_3: string | null
  description_1: string
  description_2: string | null
  path_1: string | null
  path_2: string | null
  final_url: string
  call_to_action: string | null
  variation_name: string | null
  is_primary: boolean
  is_ai_generated: boolean
  platform_ad_id: string | null
}

export interface CampaignCreateRequest {
  name: string
  description?: string | null
  ad_account_id: string
  objective: string
  budget_type?: string
  budget_amount: number | string
  budget_currency?: string
  start_date?: string | null
  end_date?: string | null
  is_ongoing?: boolean
  targeting?: Record<string, unknown> | null
  platform_settings?: Record<string, unknown> | null
  ad_copies?: AdCopyCreate[]
}

export interface CampaignUpdateRequest {
  name?: string | null
  description?: string | null
  objective?: string | null
  budget_type?: string | null
  budget_amount?: number | string | null
  start_date?: string | null
  end_date?: string | null
  is_ongoing?: boolean | null
  targeting?: Record<string, unknown> | null
  platform_settings?: Record<string, unknown> | null
}

export interface CampaignResponse {
  id: string
  name: string
  description: string | null
  platform: string
  objective: string
  status: string
  status_reason: string | null
  budget_type: string
  budget_amount: number
  budget_currency: string
  start_date: string | null
  end_date: string | null
  is_ongoing: boolean
  targeting: Record<string, unknown> | null
  platform_settings: Record<string, unknown> | null
  platform_campaign_id: string | null
  platform_status: string | null
  last_synced_at: string | null
  ad_account_id: string
  org_id: string
  version: number
  created_by_id: string | null
  approved_by_id: string | null
  approved_at: string | null
  created_at: string
  updated_at: string
  ad_copies: AdCopyResponse[]
}

export interface CampaignListResponse {
  campaigns: CampaignResponse[]
  total: number
  page: number
  page_size: number
}

export interface CampaignListParams {
  status_filter?: string
  platform_filter?: string
  search?: string
  page?: number
  page_size?: number
}

export interface BulkActionResponse {
  success_count: number
  failure_count: number
  failures: Record<string, unknown>[]
}

export interface CSVImportResponse {
  created_count: number
  error_count: number
  errors: Record<string, unknown>[]
  campaign_ids: string[]
}

// ---- AI --------------------------------------------------------------------

export interface FullAdCopyGenerationRequest {
  product: string
  audience: string
  benefits: string
  objective: string
  url: string
  platform?: string
  num_variations?: number
  additional_context?: string | null
  campaign_id?: string | null
}

export interface FullAdCopyVariation {
  headline_1: string
  headline_2?: string | null
  headline_3?: string | null
  description_1: string
  description_2?: string | null
  cta: string
  variation_name: string
}

export interface FullAdCopyGenerationResponse {
  variations: FullAdCopyVariation[]
  ai_assisted: boolean
  metadata: {
    model: string
    provider: string
    tokens_used: number
    estimated_cost: number
    generation_time_ms: number
    fallback_used: boolean
  }
  platform_limits: Record<string, unknown>
}

export interface AIUsageLimits {
  generations_used: number
  generation_limit: number
  remaining_generations: number
  usage_percentage: number
  tokens_used: number
  estimated_cost_usd: number
  plan_tier: string
  is_limit_reached: boolean
  should_warn: boolean
}

// ---- Analitik --------------------------------------------------------------

export interface MetricsSummary {
  impressions: number
  clicks: number
  ctr: number
  spend: number
  conversions: number
  conversion_value: number
  cpa: number
  roas: number
  avg_cpc: number
  avg_cpm: number
}

export interface MetricsComparison {
  current: MetricsSummary
  previous?: MetricsSummary | null
  change_percent: Record<string, number>
}

export interface CampaignMetrics {
  campaign_id: string
  campaign_name: string
  platform: string
  status: string
  metrics: MetricsSummary
}

export interface CampaignMetricsList {
  campaigns: CampaignMetrics[]
  total: number
  page: number
  page_size: number
}

export interface TimeSeriesPoint {
  timestamp: string
  impressions: number
  clicks: number
  spend: number
  conversions: number
  conversion_value: number
}

export interface TimeSeriesData {
  data: TimeSeriesPoint[]
  granularity: string
  start_date: string
  end_date: string
}

export interface PlatformMetrics {
  campaign_count: number
  impressions: number
  clicks: number
  spend: number
  conversions: number
  conversion_value: number
  ctr: number
  cpc: number
  cpa: number
  roas: number
  spend_share: number
}

export interface PlatformComparisonResponse {
  platforms: Record<string, PlatformMetrics>
  totals: Record<string, number>
  period: Record<string, string>
}

export interface DateRangeParams {
  start_date?: string
  end_date?: string
}

// ---- Uyarılar --------------------------------------------------------------

export interface Alert {
  id: string
  name: string
  description: string | null
  alert_type: string
  config: Record<string, unknown>
  scope_type: string
  campaign_id: string | null
  notification_channels: Record<string, unknown>
  is_enabled: boolean
  is_triggered: boolean
  last_triggered_at: string | null
  cooldown_minutes: number
  created_at: string
}

export interface AlertCreate {
  name: string
  description?: string | null
  alert_type: string
  config: Record<string, unknown>
  scope_type?: string
  campaign_id?: string | null
  notification_channels?: Record<string, unknown> | null
  cooldown_minutes?: number
}

export interface AlertUpdate {
  name?: string | null
  description?: string | null
  config?: Record<string, unknown> | null
  notification_channels?: Record<string, unknown> | null
  cooldown_minutes?: number | null
  is_enabled?: boolean | null
}

// ---- Otomasyon -------------------------------------------------------------

export interface AutomationCondition {
  metric: string
  operator: string
  /** Backend'de `value` olarak saklanır; istemci katmanı çevirir. */
  threshold: number
  lookback_days?: number
}

export interface AutomationAction {
  type: string
  params?: Record<string, unknown>
}

export interface AutomationConditions {
  operator?: string
  conditions: AutomationCondition[]
}

export interface AutomationRule {
  id: string
  name: string
  description: string | null
  status: string
  scope_type: string
  campaign_id: string | null
  platform: string | null
  conditions: AutomationConditions
  condition_logic: string
  actions: AutomationAction[]
  requires_approval: boolean
  approval_timeout_hours: number
  cooldown_minutes: number
  max_executions_per_day: number | null
  is_one_time: boolean
  schedule: Record<string, unknown> | null
  template_id: string | null
  last_evaluated_at: string | null
  last_triggered_at: string | null
  execution_count: number
  created_at: string
}

export interface AutomationRuleCreate {
  name: string
  description?: string
  scope_type?: string
  campaign_id?: string | null
  platform?: string | null
  conditions: AutomationConditions
  actions: AutomationAction[]
  requires_approval?: boolean
  approval_timeout_hours?: number
  cooldown_minutes?: number
  max_executions_per_day?: number | null
  is_one_time?: boolean
}

export interface PendingAction {
  id: string
  rule_id: string
  rule_name: string
  campaign_id: string | null
  campaign_name?: string | null
  action_type: string
  action_params: Record<string, unknown>
  trigger_reason: string
  status: string
  created_at: string
  expires_at: string
  resolved_at: string | null
  resolved_by_id: string | null
}

export interface TemplateParameter {
  name: string
  label?: string
  type?: string
  description?: string
  required?: boolean
  default_value?: unknown
}

export interface RuleTemplate {
  id: string
  name: string
  description: string
  category: string
  conditions_template: Record<string, unknown>
  actions_template: unknown[]
  default_requires_approval: boolean
  default_cooldown_minutes: number
  parameters: TemplateParameter[]
  applicable_platforms: string[]
}

export interface ConditionType {
  label: string
  unit: string
  operators: string[]
}

export interface ActionType {
  label: string
  description: string
  params: string[]
}

// ---- Faturalama ------------------------------------------------------------

export interface SubscriptionResponse {
  id: string
  plan_tier: string
  status: string
  billing_cycle: string
  amount: number
  currency: string
  current_period_start: string | null
  current_period_end: string | null
  trial_end: string | null
  cancel_at_period_end: boolean
  canceled_at: string | null
}

export interface PlanInfo {
  id: string
  name: string
  description: string
  /** Cent cinsinden; null ise "satışla iletişime geçin" */
  price_monthly: number | null
  price_yearly: number | null
  price_id_monthly?: string
  price_id_yearly?: string
  limits: Record<string, number>
}

export interface InvoiceResponse {
  id: string
  invoice_number: string | null
  status: string
  amount_due: number
  amount_paid: number
  total: number
  currency: string
  description: string | null
  hosted_invoice_url: string | null
  invoice_pdf: string | null
  period_start: string | null
  period_end: string | null
  created_at: string
}

export interface PaymentMethodResponse {
  id: string
  type: string
  card_brand: string | null
  card_last4: string | null
  card_exp_month: number | null
  card_exp_year: number | null
  is_default: boolean
}

export interface UsageSummaryResponse {
  period_start: string
  period_end: string
  usage: Record<string, number>
  limits: Record<string, number>
}

export interface CheckoutRequest {
  price_id: string
  success_url: string
  cancel_url: string
}

// ---- Bildirimler -----------------------------------------------------------

export interface NotificationItem {
  id: string
  title: string
  message: string
  notification_type: string
  related_entity_type: string | null
  related_entity_id: string | null
  data: Record<string, unknown> | null
  is_read: boolean
  read_at: string | null
  created_at: string
}

export interface NotificationListResponse {
  notifications: NotificationItem[]
  total: number
  unread_count: number
}

// =============================================================================
// API grupları
// =============================================================================

export const authApi = {
  login: (email: string, password: string) =>
    request<LoginResponse>('/auth/login', {
      method: 'POST',
      body: { email, password },
      auth: false,
    }),

  register: (data: RegisterRequest) =>
    request<RegisterResponse>('/auth/register', { method: 'POST', body: data, auth: false }),

  requestPasswordReset: (email: string) =>
    request<void>('/auth/password-reset/request', {
      method: 'POST',
      body: { email },
      auth: false,
    }),

  logout: () => request<void>('/auth/logout', { method: 'POST' }),
}

export const userApi = {
  getProfile: () => request<UserProfile>('/users/me'),

  updateProfile: (data: UpdateProfileRequest) =>
    request<void>('/users/me', { method: 'PATCH', body: data }),
}

export const connectionsApi = {
  listConnections: () => request<AdAccountListResponse>('/connections'),

  initiateConnection: (platform: 'google' | 'meta' | 'tiktok') =>
    request<ConnectResponse>('/connections/connect', { method: 'POST', body: { platform } }),

  getAvailableAccounts: (platform: string, state: string) =>
    request<AvailableAccountsResponse>(`/connections/${platform}/accounts`, { query: { state } }),

  selectAccounts: (platform: string, state: string, accountIds: string[]) =>
    request<void>(`/connections/callback/${platform}/select`, {
      method: 'POST',
      query: { state },
      body: { account_ids: accountIds },
    }),

  disconnectAccount: (accountId: string) =>
    request<void>(`/connections/${accountId}`, { method: 'DELETE' }),

  triggerSync: (accountId: string) =>
    request<void>(`/connections/${accountId}/sync`, { method: 'POST' }),

  refreshToken: (accountId: string) =>
    request<void>(`/connections/${accountId}/refresh-token`, { method: 'POST' }),
}

export const campaignsApi = {
  listCampaigns: (params?: CampaignListParams) =>
    request<CampaignListResponse>('/campaigns', { query: params }),

  getCampaign: (id: string) => request<CampaignResponse>(`/campaigns/${id}`),

  createCampaign: (data: CampaignCreateRequest) =>
    request<CampaignResponse>('/campaigns', { method: 'POST', body: data }),

  updateCampaign: (id: string, data: CampaignUpdateRequest) =>
    request<CampaignResponse>(`/campaigns/${id}`, { method: 'PATCH', body: data }),

  deleteCampaign: (id: string) => request<void>(`/campaigns/${id}`, { method: 'DELETE' }),

  submitForApproval: (id: string, comment?: string) =>
    request<CampaignResponse>(`/campaigns/${id}/submit`, { method: 'POST', body: { comment } }),

  approveCampaign: (id: string, comment?: string) =>
    request<CampaignResponse>(`/campaigns/${id}/approve`, { method: 'POST', body: { comment } }),

  rejectCampaign: (id: string, comment?: string) =>
    request<CampaignResponse>(`/campaigns/${id}/reject`, { method: 'POST', body: { comment } }),

  pauseCampaign: (id: string) =>
    request<CampaignResponse>(`/campaigns/${id}/pause`, { method: 'POST' }),

  resumeCampaign: (id: string) =>
    request<CampaignResponse>(`/campaigns/${id}/resume`, { method: 'POST' }),

  duplicateCampaign: (id: string) =>
    request<CampaignResponse>(`/campaigns/${id}/duplicate`, { method: 'POST' }),

  bulkAction: (campaignIds: string[], action: string) =>
    request<BulkActionResponse>('/campaigns/bulk-action', {
      method: 'POST',
      body: { campaign_ids: campaignIds, action },
    }),

  syncCampaign: (id: string) =>
    request<CampaignResponse>(`/campaigns/${id}/sync`, { method: 'POST' }),

  pushCampaign: (id: string) =>
    request<CampaignResponse>(`/campaigns/${id}/push`, { method: 'POST' }),

  /** Backend ham CSV metnini gövde olarak bekler (multipart değil). */
  importCsv: (csvContent: string) =>
    request<CSVImportResponse>('/campaigns/import-csv', {
      method: 'POST',
      rawBody: { content: csvContent, contentType: 'text/csv' },
    }),
}

export const aiApi = {
  getUsageLimits: () => request<AIUsageLimits>('/ai/limits'),

  generateFullAdCopy: (data: FullAdCopyGenerationRequest) =>
    request<FullAdCopyGenerationResponse>('/ai/generate-ad-copy', { method: 'POST', body: data }),
}

export const analyticsApi = {
  getOverview: (params?: DateRangeParams & { compare_previous?: boolean }) =>
    request<MetricsComparison>('/analytics/overview', { query: params }),

  getCampaignsList: (params?: DateRangeParams & { page?: number; page_size?: number }) =>
    request<CampaignMetricsList>('/analytics/campaigns', { query: params }),

  getTimeSeries: (
    params?: DateRangeParams & { granularity?: string; campaign_id?: string }
  ) => request<TimeSeriesData>('/analytics/time-series', { query: params }),

  getPlatformComparison: (params?: DateRangeParams) =>
    request<PlatformComparisonResponse>('/analytics/platform-comparison', { query: params }),
}

export const exportsApi = {
  downloadOverviewCsv: (params?: DateRangeParams & { include_comparison?: boolean }) =>
    request<Blob>('/exports/csv/overview', { query: params, responseType: 'blob' }),

  downloadCampaignsCsv: (params?: DateRangeParams) =>
    request<Blob>('/exports/csv/campaigns', { query: params, responseType: 'blob' }),

  downloadTimeseriesCsv: (
    params?: DateRangeParams & { granularity?: string; campaign_id?: string }
  ) => request<Blob>('/exports/csv/timeseries', { query: params, responseType: 'blob' }),

  downloadPdfReport: (params?: DateRangeParams & { title?: string }) =>
    request<Blob>('/exports/pdf/report', { query: params, responseType: 'blob' }),
}

export const alertsApi = {
  listAlerts: (params?: { is_enabled?: boolean; alert_type?: string; page?: number; page_size?: number }) =>
    request<{ alerts: Alert[]; total: number }>('/alerts', { query: params }),

  createAlert: (data: AlertCreate) => request<Alert>('/alerts', { method: 'POST', body: data }),

  updateAlert: (id: string, data: AlertUpdate) =>
    request<Alert>(`/alerts/${id}`, { method: 'PATCH', body: data }),

  deleteAlert: (id: string) => request<void>(`/alerts/${id}`, { method: 'DELETE' }),
}

// Backend koşullarda `value`, frontend `threshold` kullanır; sınırda çeviriyoruz.
interface BackendRule extends Omit<AutomationRule, 'conditions'> {
  conditions: {
    operator?: string
    conditions?: Array<Omit<AutomationCondition, 'threshold'> & { value?: number; threshold?: number }>
  }
}

function fromBackendRule(rule: BackendRule): AutomationRule {
  return {
    ...rule,
    conditions: {
      operator: rule.conditions?.operator,
      conditions: (rule.conditions?.conditions ?? []).map((c) => ({
        metric: c.metric,
        operator: c.operator,
        threshold: c.threshold ?? c.value ?? 0,
        lookback_days: c.lookback_days,
      })),
    },
  }
}

function toBackendConditions(conditions: AutomationConditions) {
  return {
    operator: conditions.operator,
    conditions: conditions.conditions.map((c) => ({
      metric: c.metric,
      operator: c.operator,
      value: c.threshold,
      lookback_days: c.lookback_days,
    })),
  }
}

export const automationApi = {
  listRules: async (params?: { status?: string; campaign_id?: string; page?: number; page_size?: number }) => {
    const res = await request<{ rules: BackendRule[]; total: number }>('/automation/rules', {
      query: params,
    })
    return { rules: res.rules.map(fromBackendRule), total: res.total }
  },

  createRule: async (data: AutomationRuleCreate) =>
    fromBackendRule(
      await request<BackendRule>('/automation/rules', {
        method: 'POST',
        body: { ...data, conditions: toBackendConditions(data.conditions) },
      })
    ),

  deleteRule: (id: string) => request<void>(`/automation/rules/${id}`, { method: 'DELETE' }),

  activateRule: async (id: string) =>
    fromBackendRule(await request<BackendRule>(`/automation/rules/${id}/activate`, { method: 'POST' })),

  pauseRule: async (id: string) =>
    fromBackendRule(await request<BackendRule>(`/automation/rules/${id}/pause`, { method: 'POST' })),

  runRule: (id: string, campaignId?: string) =>
    request<Record<string, unknown>>(`/automation/rules/${id}/run`, {
      method: 'POST',
      query: { campaign_id: campaignId },
    }),

  /** Backend `actions` döndürür; frontend `pending_actions` bekler. */
  getPendingActions: async (params?: { status?: string; page?: number; page_size?: number }) => {
    const res = await request<{ actions: PendingAction[]; total: number }>(
      '/automation/pending-actions',
      { query: params }
    )
    return { pending_actions: res.actions, total: res.total }
  },

  approvePendingAction: (id: string, note?: string) =>
    request<void>(`/automation/pending-actions/${id}/approve`, { method: 'POST', body: { note } }),

  rejectPendingAction: (id: string, note?: string) =>
    request<void>(`/automation/pending-actions/${id}/reject`, { method: 'POST', body: { note } }),

  getTemplates: (category?: string) =>
    request<{ templates: RuleTemplate[] }>('/automation/templates', { query: { category } }),

  createRuleFromTemplate: async (
    templateId: string,
    data: { name: string; parameter_values: Record<string, unknown>; campaign_id?: string | null }
  ) =>
    fromBackendRule(
      await request<BackendRule>(`/automation/templates/${templateId}/create-rule`, {
        method: 'POST',
        body: data,
      })
    ),

  getConditionTypes: () =>
    request<{ condition_types: Record<string, ConditionType>; operators: Record<string, string> }>(
      '/automation/metadata/conditions'
    ),

  getActionTypes: () =>
    request<{ action_types: Record<string, ActionType> }>('/automation/metadata/actions'),
}

export const billingApi = {
  getSubscription: () => request<SubscriptionResponse>('/billing/subscription'),

  getPlans: () => request<{ plans: PlanInfo[] }>('/billing/plans'),

  getInvoices: (params?: { page?: number; page_size?: number }) =>
    request<{ invoices: InvoiceResponse[]; total: number; page: number; page_size: number }>(
      '/billing/invoices',
      { query: params }
    ),

  getPaymentMethods: () => request<PaymentMethodResponse[]>('/billing/payment-methods'),

  getUsage: () => request<UsageSummaryResponse>('/billing/usage'),

  createCheckout: (data: CheckoutRequest) =>
    request<{ checkout_url: string }>('/billing/checkout', { method: 'POST', body: data }),

  createPortalSession: (returnUrl: string) =>
    request<{ portal_url: string }>('/billing/portal', {
      method: 'POST',
      body: { return_url: returnUrl },
    }),

  deletePaymentMethod: (id: string) =>
    request<void>(`/billing/payment-methods/${id}`, { method: 'DELETE' }),
}

export const notificationsApi = {
  list: (params?: { is_read?: boolean; page?: number; page_size?: number }) =>
    request<NotificationListResponse>('/notifications', { query: params }),

  markAsRead: (id: string) => request<void>(`/notifications/${id}/read`, { method: 'POST' }),

  markAllAsRead: () => request<void>('/notifications/read-all', { method: 'POST' }),
}
