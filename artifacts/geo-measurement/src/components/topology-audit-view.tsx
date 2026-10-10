import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  CheckCircle2,
  Filter,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  XCircle,
  HelpCircle,
  MapPin,
} from 'lucide-react';
import {
  fetchTopologyAudit,
  type TopologyAuditResponse,
  type TopologyIssue,
} from '@/lib/analytics-api';

interface TopologyAuditViewProps {
  fileId: string;
  featureCount: number;
}

export function TopologyAuditView({ fileId }: TopologyAuditViewProps) {
  const [severityFilter, setSeverityFilter] = useState<'all' | 'error' | 'warning'>('all');
  const [search, setSearch] = useState('');

  const {
    data: audit,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery<TopologyAuditResponse>({
    queryKey: ['topology-audit', fileId],
    queryFn: () => fetchTopologyAudit(fileId),
    enabled: !!fileId,
    staleTime: 60_000,
  });

  if (isLoading) {
    return (
      <div className="space-y-4 py-8">
        <div className="flex items-center justify-center gap-3 text-sm text-muted-foreground">
          <RefreshCw className="h-5 w-5 animate-spin text-primary" />
          <span>Auditing polygon topology & geometry integrity...</span>
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-muted/60" />
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-xl border border-destructive/20 bg-destructive/5 p-6 text-center">
        <AlertTriangle className="mx-auto h-8 w-8 text-destructive" />
        <h4 className="mt-2 text-sm font-bold text-destructive">Topology Audit Failed</h4>
        <p className="mt-1 text-xs text-muted-foreground">
          {error instanceof Error ? error.message : 'Unable to complete geometry inspection.'}
        </p>
        <button
          onClick={() => refetch()}
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-semibold hover:bg-secondary"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Retry audit
        </button>
      </div>
    );
  }

  if (!audit) return null;

  const score = Math.round(audit.quality_score);
  const grade =
    score >= 90
      ? { label: 'EXCELLENT', tone: 'bg-emerald-500/15 text-emerald-700 border-emerald-500/30' }
      : score >= 75
      ? { label: 'GOOD', tone: 'bg-blue-500/15 text-blue-700 border-blue-500/30' }
      : score >= 50
      ? { label: 'FAIR', tone: 'bg-amber-500/15 text-amber-700 border-amber-500/30' }
      : { label: 'POOR', tone: 'bg-rose-500/15 text-rose-700 border-rose-500/30' };

  const filteredIssues = audit.issues.filter((issue) => {
    if (severityFilter !== 'all' && issue.severity !== severityFilter) return false;
    if (search.trim()) {
      const q = search.toLowerCase();
      return (
        issue.issue_type.toLowerCase().includes(q) ||
        issue.description.toLowerCase().includes(q) ||
        String(issue.feature_index).includes(q)
      );
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Top Banner with Quality Score & Summary */}
      <div className="grid gap-4 md:grid-cols-4">
        {/* Score Card */}
        <div className="flex flex-col justify-between rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[9px] uppercase tracking-[.15em] text-muted-foreground">
              Topology Health
            </span>
            {score >= 80 ? (
              <ShieldCheck className="h-4 w-4 text-emerald-600" />
            ) : (
              <ShieldAlert className="h-4 w-4 text-amber-600" />
            )}
          </div>
          <div className="my-2 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold tracking-tight">{score}</span>
            <span className="text-xs text-muted-foreground">/ 100</span>
            <span className={`ml-auto rounded-full border px-2 py-0.5 font-mono text-[9px] font-bold ${grade.tone}`}>
              {grade.label}
            </span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
            <div
              className={`h-full transition-all duration-500 ${
                score >= 80 ? 'bg-emerald-600' : score >= 50 ? 'bg-amber-500' : 'bg-rose-600'
              }`}
              style={{ width: `${score}%` }}
            />
          </div>
        </div>

        {/* Audited Count */}
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[9px] uppercase tracking-[.15em] text-muted-foreground">
              Audited Features
            </span>
            <CheckCircle2 className="h-4 w-4 text-primary" />
          </div>
          <div className="mt-3 text-2xl font-extrabold">{audit.audited_count.toLocaleString()}</div>
          <div className="mt-1 text-[10px] text-muted-foreground">
            {audit.feature_count} features present in file
          </div>
        </div>

        {/* Errors Count */}
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[9px] uppercase tracking-[.15em] text-muted-foreground">
              Topology Errors
            </span>
            <XCircle className={`h-4 w-4 ${audit.error_count > 0 ? 'text-destructive' : 'text-muted-foreground'}`} />
          </div>
          <div className={`mt-3 text-2xl font-extrabold ${audit.error_count > 0 ? 'text-destructive' : 'text-foreground'}`}>
            {audit.error_count}
          </div>
          <div className="mt-1 text-[10px] text-muted-foreground">
            Self-intersections, bow-ties, null shapes
          </div>
        </div>

        {/* Warnings Count */}
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[9px] uppercase tracking-[.15em] text-muted-foreground">
              Topology Warnings
            </span>
            <AlertTriangle className={`h-4 w-4 ${audit.warning_count > 0 ? 'text-amber-600' : 'text-muted-foreground'}`} />
          </div>
          <div className={`mt-3 text-2xl font-extrabold ${audit.warning_count > 0 ? 'text-amber-700' : 'text-foreground'}`}>
            {audit.warning_count}
          </div>
          <div className="mt-1 text-[10px] text-muted-foreground">
            Slivers, spikes & duplicate vertices
          </div>
        </div>
      </div>

      {/* Filter and Findings Controls */}
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div>
            <h4 className="text-sm font-extrabold tracking-[-.02em]">Audit Findings & Defect Catalog</h4>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              Automated OGC geometric validity tests run per-feature.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center rounded-lg border border-border bg-background p-0.5 text-xs">
              <button
                onClick={() => setSeverityFilter('all')}
                className={`rounded-md px-2.5 py-1 text-[10px] font-semibold transition ${
                  severityFilter === 'all'
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                All ({audit.issues.length})
              </button>
              <button
                onClick={() => setSeverityFilter('error')}
                className={`rounded-md px-2.5 py-1 text-[10px] font-semibold transition ${
                  severityFilter === 'error'
                    ? 'bg-destructive text-destructive-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                Errors ({audit.error_count})
              </button>
              <button
                onClick={() => setSeverityFilter('warning')}
                className={`rounded-md px-2.5 py-1 text-[10px] font-semibold transition ${
                  severityFilter === 'warning'
                    ? 'bg-amber-600 text-white'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                Warnings ({audit.warning_count})
              </button>
            </div>

            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="inline-flex h-8 items-center gap-1 rounded-lg border border-border bg-background px-2.5 text-[10px] font-semibold hover:bg-secondary disabled:opacity-50"
              title="Rerun quality audit"
            >
              <RefreshCw className={`h-3 w-3 ${isFetching ? 'animate-spin' : ''}`} />
              Re-audit
            </button>
          </div>
        </div>

        {/* Issue List */}
        {audit.issues.length === 0 ? (
          <div className="rounded-xl border border-dashed border-emerald-500/30 bg-emerald-500/5 px-6 py-10 text-center">
            <ShieldCheck className="mx-auto h-10 w-10 text-emerald-600" />
            <h5 className="mt-3 text-sm font-bold text-emerald-800">100% Topologically Clean</h5>
            <p className="mx-auto mt-1 max-w-md text-xs text-muted-foreground">
              All inspected polygon rings are closed, simple, watertight, and free from self-intersections, slivers, or spike vertices.
            </p>
          </div>
        ) : filteredIssues.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border py-8 text-center text-xs text-muted-foreground">
            No issues match the selected filter.
          </div>
        ) : (
          <div className="divide-y divide-border overflow-hidden rounded-lg border border-border">
            {filteredIssues.map((issue, idx) => (
              <IssueItem key={`${issue.feature_index}-${issue.issue_type}-${idx}`} issue={issue} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function IssueItem({ issue }: { issue: TopologyIssue }) {
  const isError = issue.severity === 'error';
  return (
    <div className="flex flex-col gap-2 p-3 transition hover:bg-secondary/40 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 shrink-0">
          {isError ? (
            <XCircle className="h-4 w-4 text-destructive" />
          ) : (
            <AlertTriangle className="h-4 w-4 text-amber-600" />
          )}
        </div>
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[10px] font-bold text-foreground">
              Feature #{issue.feature_index}
            </span>
            <span
              className={`rounded px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase ${
                isError ? 'bg-destructive/10 text-destructive' : 'bg-amber-500/10 text-amber-800'
              }`}
            >
              {issue.issue_type.replace(/_/g, ' ')}
            </span>
            <span className="font-mono text-[9px] text-muted-foreground">
              {issue.geometry_type}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{issue.description}</p>
        </div>
      </div>

      {issue.locations && issue.locations.length > 0 && (
        <div className="flex shrink-0 items-center gap-1 font-mono text-[9px] text-muted-foreground sm:self-center">
          <MapPin className="h-3 w-3 text-primary" />
          {issue.locations[0].latitude != null && issue.locations[0].longitude != null ? (
            <span>
              {issue.locations[0].latitude.toFixed(5)}, {issue.locations[0].longitude.toFixed(5)}
            </span>
          ) : (
            <span>Vertex #{issue.locations[0].coordinate_index ?? '—'}</span>
          )}
        </div>
      )}
    </div>
  );
}
