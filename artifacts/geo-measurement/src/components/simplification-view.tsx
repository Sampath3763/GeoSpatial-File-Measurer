import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Sparkles,
  Zap,
  Layers,
  TrendingDown,
  RefreshCw,
  Info,
  Sliders,
  CheckCircle,
} from 'lucide-react';
import {
  fetchSimplifiedFeatures,
  type SimplificationResponse,
  type SimplifiedFeature,
} from '@/lib/analytics-api';

interface SimplificationViewProps {
  fileId: string;
  featureCount: number;
}

const TOLERANCE_PRESETS = [
  { label: 'Fine (1 m)', value: 0.00001, desc: 'Preserves subtle curves and corners' },
  { label: 'Balanced (11 m)', value: 0.0001, desc: 'Recommended default for general maps' },
  { label: 'Fast Web (110 m)', value: 0.001, desc: 'High performance for web rendering' },
  { label: 'Overview (1.1 km)', value: 0.01, desc: 'Extreme reduction for thumbnail / overview' },
];

export function SimplificationView({ fileId, featureCount }: SimplificationViewProps) {
  const [tolerance, setTolerance] = useState<number>(0.0001);
  const [limit, setLimit] = useState<number>(100);

  const {
    data: result,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery<SimplificationResponse>({
    queryKey: ['geometry-simplification', fileId, tolerance, limit],
    queryFn: () => fetchSimplifiedFeatures(fileId, tolerance, limit),
    enabled: !!fileId,
    staleTime: 60_000,
  });

  const savedVertices =
    result ? Math.max(0, result.total_original_vertices - result.total_simplified_vertices) : 0;
  const reductionPct = result ? result.overall_reduction_pct : 0;

  return (
    <div className="space-y-6">
      {/* Top Configuration Bar: Tolerance presets & Slider */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
          <div>
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              <h4 className="text-sm font-extrabold tracking-[-.02em]">
                Douglas-Peucker Geometry Simplification
              </h4>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Reduces vertex density while preserving shape topology and boundary accuracy for high-speed rendering.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              Tolerance: <span className="font-bold text-foreground">{tolerance}</span>
            </span>
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="inline-flex h-8 items-center gap-1 rounded-lg border border-border bg-background px-2.5 text-[10px] font-semibold hover:bg-secondary disabled:opacity-50"
            >
              <RefreshCw className={`h-3 w-3 ${isFetching ? 'animate-spin' : ''}`} />
              Recalculate
            </button>
          </div>
        </div>

        {/* Preset Buttons */}
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {TOLERANCE_PRESETS.map((preset) => {
            const isSelected = tolerance === preset.value;
            return (
              <button
                key={preset.value}
                onClick={() => setTolerance(preset.value)}
                className={`flex flex-col items-start rounded-lg border p-2.5 text-left transition ${
                  isSelected
                    ? 'border-primary bg-primary/10 text-primary ring-1 ring-primary/30'
                    : 'border-border bg-background hover:bg-secondary/60 text-muted-foreground hover:text-foreground'
                }`}
              >
                <div className="flex items-center justify-between w-full">
                  <span className="text-xs font-bold">{preset.label}</span>
                  {isSelected && <CheckCircle className="h-3 w-3 text-primary" />}
                </div>
                <span className="mt-1 font-mono text-[9px] opacity-75">{preset.desc}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Loading & Error States */}
      {isLoading ? (
        <div className="py-12 text-center">
          <RefreshCw className="mx-auto h-6 w-6 animate-spin text-primary" />
          <p className="mt-3 text-xs text-muted-foreground">
            Applying Douglas-Peucker decimation across features...
          </p>
        </div>
      ) : isError ? (
        <div className="rounded-xl border border-destructive/20 bg-destructive/5 p-6 text-center">
          <p className="text-xs font-bold text-destructive">
            {error instanceof Error ? error.message : 'Could not compute geometry simplification.'}
          </p>
          <button
            onClick={() => refetch()}
            className="mt-3 text-xs font-semibold text-primary underline underline-offset-4"
          >
            Try again
          </button>
        </div>
      ) : result ? (
        <>
          {/* Impact Metric Cards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {/* Original Vertices */}
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center justify-between">
                <span className="font-mono text-[9px] uppercase tracking-[.15em] text-muted-foreground">
                  Original Vertices
                </span>
                <Layers className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="mt-2 text-2xl font-extrabold tracking-tight">
                {result.total_original_vertices.toLocaleString()}
              </div>
              <div className="mt-1 text-[10px] text-muted-foreground">
                Raw source coordinates
              </div>
            </div>

            {/* Simplified Vertices */}
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center justify-between">
                <span className="font-mono text-[9px] uppercase tracking-[.15em] text-muted-foreground">
                  Simplified Vertices
                </span>
                <Zap className="h-4 w-4 text-primary" />
              </div>
              <div className="mt-2 text-2xl font-extrabold tracking-tight text-primary">
                {result.total_simplified_vertices.toLocaleString()}
              </div>
              <div className="mt-1 text-[10px] text-muted-foreground">
                Optimized web coordinates
              </div>
            </div>

            {/* Vertices Eliminated */}
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center justify-between">
                <span className="font-mono text-[9px] uppercase tracking-[.15em] text-muted-foreground">
                  Vertices Removed
                </span>
                <TrendingDown className="h-4 w-4 text-emerald-600" />
              </div>
              <div className="mt-2 text-2xl font-extrabold tracking-tight text-emerald-700">
                -{savedVertices.toLocaleString()}
              </div>
              <div className="mt-1 text-[10px] text-muted-foreground">
                Redundant coordinate points saved
              </div>
            </div>

            {/* Reduction Ratio */}
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center justify-between">
                <span className="font-mono text-[9px] uppercase tracking-[.15em] text-muted-foreground">
                  Payload Reduction
                </span>
                <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 font-mono text-[9px] font-bold text-emerald-700">
                  ⚡ Fast
                </span>
              </div>
              <div className="mt-2 text-2xl font-extrabold tracking-tight text-emerald-700">
                {reductionPct.toFixed(1)}%
              </div>
              <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                <div
                  className="h-full bg-emerald-600 transition-all duration-500"
                  style={{ width: `${Math.min(100, reductionPct)}%` }}
                />
              </div>
            </div>
          </div>

          {/* Per-feature Simplification Table */}
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            <div className="border-b border-border px-5 py-3.5">
              <h5 className="text-xs font-extrabold tracking-[-.02em]">
                Per-Feature Simplification Breakdown
              </h5>
              <p className="mt-0.5 text-[10px] text-muted-foreground">
                Showing top {result.features.length} simplified features.
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[600px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-border bg-background font-mono text-[9px] uppercase tracking-[.12em] text-muted-foreground">
                    <th className="px-4 py-2.5 font-medium">Feature #</th>
                    <th className="px-4 py-2.5 font-medium">Geometry</th>
                    <th className="px-4 py-2.5 font-medium">Original Points</th>
                    <th className="px-4 py-2.5 font-medium">Simplified Points</th>
                    <th className="px-4 py-2.5 font-medium">Reduction</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {result.features.map((feat) => (
                    <tr
                      key={feat.feature_index}
                      className="text-xs transition-colors hover:bg-secondary/35"
                    >
                      <td className="px-4 py-2.5 font-mono text-[10px] font-medium">
                        #{feat.feature_index}
                      </td>
                      <td className="px-4 py-2.5 font-medium">{feat.geometry_type}</td>
                      <td className="px-4 py-2.5 font-mono text-[10px]">
                        {feat.original_vertex_count.toLocaleString()}
                      </td>
                      <td className="px-4 py-2.5 font-mono text-[10px] font-semibold text-primary">
                        {feat.simplified_vertex_count.toLocaleString()}
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[10px] font-bold text-emerald-700">
                            -{feat.reduction_pct.toFixed(1)}%
                          </span>
                          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-secondary">
                            <div
                              className="h-full bg-emerald-600"
                              style={{ width: `${Math.min(100, feat.reduction_pct)}%` }}
                            />
                          </div>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
