export type AreaUnit = 'sq_m' | 'sq_km' | 'sq_ft' | 'sq_mi' | 'hectares' | 'acres';
export type LengthUnit = 'm' | 'km' | 'ft' | 'mi' | 'nautical_miles';

export const AREA_UNIT_LABELS: Record<AreaUnit, string> = {
  sq_m: 'm²',
  hectares: 'ha',
  acres: 'ac',
  sq_km: 'km²',
  sq_ft: 'sq ft',
  sq_mi: 'sq mi',
};

export const LENGTH_UNIT_LABELS: Record<LengthUnit, string> = {
  m: 'm',
  km: 'km',
  ft: 'ft',
  mi: 'mi',
  nautical_miles: 'NM',
};

export interface UnitValue {
  value: number;
  label: string;
}

export interface AreaBreakdown {
  sq_m: UnitValue;
  sq_km: UnitValue;
  sq_ft: UnitValue;
  sq_mi: UnitValue;
  hectares: UnitValue;
  acres: UnitValue;
}

export interface LengthBreakdown {
  m: UnitValue;
  km: UnitValue;
  ft: UnitValue;
  mi: UnitValue;
  nautical_miles: UnitValue;
}

export interface FeatureUnitMeasurement {
  feature_index: number;
  layer?: string | null;
  geometry_type: string;
  measurement_status: 'CALCULATED' | 'NOT_APPLICABLE' | 'UNSUPPORTED' | 'ERROR';
  area?: AreaBreakdown | null;
  length?: LengthBreakdown | null;
  projected_crs?: string | null;
  method?: string | null;
  note?: string | null;
}

export interface MultiUnitMeasurementsResponse {
  file_id: string;
  status: string;
  crs?: string | null;
  feature_count: number;
  summary: {
    total_area: AreaBreakdown;
    total_length: LengthBreakdown;
    counts_by_geometry_type: Record<string, number>;
    counts_by_measurement_status: Record<string, number>;
  };
  pagination: { limit: number; offset: number; returned: number };
  features: FeatureUnitMeasurement[];
  filtered_total: number;
}

export interface IssueLocation {
  coordinate_index?: number | null;
  longitude?: number | null;
  latitude?: number | null;
  description: string;
}

export interface TopologyIssue {
  issue_type: string;
  severity: 'error' | 'warning' | 'info';
  feature_index: number;
  geometry_type: string;
  description: string;
  locations: IssueLocation[];
}

export interface TopologyAuditResponse {
  file_id: string;
  feature_count: number;
  audited_count: number;
  quality_score: number;
  error_count: number;
  warning_count: number;
  issues: TopologyIssue[];
}

export interface SimplifiedFeature {
  feature_index: number;
  geometry_type: string;
  original_vertex_count: number;
  simplified_vertex_count: number;
  reduction_pct: number;
  geometry?: any;
}

export interface SimplificationResponse {
  file_id: string;
  tolerance: number;
  feature_count: number;
  total_original_vertices: number;
  total_simplified_vertices: number;
  overall_reduction_pct: number;
  features: SimplifiedFeature[];
}

// ---------------------------------------------------------------------------
// API Client Functions
// ---------------------------------------------------------------------------

export async function fetchMultiUnitMeasurements(
  fileId: string,
  params?: { limit?: number; offset?: number; geometry_type?: string }
): Promise<MultiUnitMeasurementsResponse> {
  const query = new URLSearchParams();
  if (params?.limit) query.set('limit', String(params.limit));
  if (params?.offset != null) query.set('offset', String(params.offset));
  if (params?.geometry_type) query.set('geometry_type', params.geometry_type);

  const url = `/api/files/${encodeURIComponent(fileId)}/measurements/units/?${query.toString()}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch multi-unit measurements (${res.status})`);
  }
  return res.json();
}

export async function fetchTopologyAudit(
  fileId: string,
  limit: number = 500
): Promise<TopologyAuditResponse> {
  const url = `/api/files/${encodeURIComponent(fileId)}/quality-audit/?limit=${limit}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch topology audit (${res.status})`);
  }
  return res.json();
}

export async function fetchSimplifiedFeatures(
  fileId: string,
  tolerance: number = 0.0001,
  limit: number = 250,
  geometryType?: string
): Promise<SimplificationResponse> {
  const query = new URLSearchParams({
    tolerance: String(tolerance),
    limit: String(limit),
  });
  if (geometryType) query.set('geometry_type', geometryType);

  const url = `/api/files/${encodeURIComponent(fileId)}/features/simplified/?${query.toString()}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to simplify features (${res.status})`);
  }
  return res.json();
}

export function getPdfReportUrl(fileId: string): string {
  return `/api/files/${encodeURIComponent(fileId)}/report`;
}

export async function downloadPdfReport(fileId: string, filename: string): Promise<void> {
  const url = getPdfReportUrl(fileId);
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to download report (${res.status})`);
  }
  const blob = await res.blob();
  const blobUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  const safeName = filename.replace(/[^\w\-.]/g, '_');
  a.download = `${safeName}_measurement_report.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(blobUrl);
}
