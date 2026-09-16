export interface ApiSuccess<T> {
  data: T;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  fields?: Record<string, string | string[]>;
}

export interface SessionData {
  user: {
    id: number;
    username: string;
  };
  scheduler: "healthy" | "unhealthy";
}

export interface SiteData {
  id?: number;
  code?: string;
  name: string;
  region: string;
}

export interface ProductSummary {
  id: number;
  name: string;
  url: string;
  image_url?: string | null;
  site: SiteData;
  stock_status: string;
  stock_status_label?: string;
  enabled: boolean;
  last_checked_at: string | null;
}

export interface VariantData {
  id: number;
  name: string;
  price: string | null;
  currency: string;
  status: string;
}

export interface ProductData extends ProductSummary {
  variants: VariantData[];
  last_error?: boolean;
  created_at?: string;
  snapshots?: Array<{
    variant_name: string;
    observed_status: string;
    price: string | null;
    currency: string;
    checked_at: string | null;
  }>;
}

export interface DashboardData {
  monitored_products: number;
  in_stock_variants: number;
  restocks_24h: number;
  failures_24h: number;
  active_failures: number;
  recent_products: ProductSummary[];
  recent_events: EventData[];
  recent_failures: FailureData[];
  pending_failures: FailureData[];
  region_summaries: RegionDashboardData[];
}

export interface RegionDashboardData {
  region: string;
  label: string;
  monitored_products: number;
  in_stock_variants: number;
  restocks_24h: number;
  failures_24h: number;
  active_failures: number;
  last_checked_at: string | null;
  products: ProductSummary[];
}

export interface EventData {
  id: number;
  product: { id: number; name: string; site_name?: string };
  site?: SiteData;
  variant: { id: number; name: string };
  old_status?: string;
  new_status?: string;
  price: string | null;
  currency?: string;
  created_at?: string;
  timestamp?: string;
  notifications?: { total: number; success: number; failed: number };
}

export interface FailureData {
  id: string | number;
  kind?: "crawl" | "notification";
  product: { id: number; name: string; site_name?: string };
  site?: SiteData;
  error_type?: string;
  message: string;
  occurred_at: string;
}

export interface NotificationChannelData {
  id: number;
  platform: "feishu" | "dingtalk";
  name: string;
  regions: string[];
  enabled: boolean;
  receive_scope_label?: string;
  webhook_configured?: boolean;
  webhook_mask?: string | null;
  secret_configured?: boolean;
}

export interface PaginatedData<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}
