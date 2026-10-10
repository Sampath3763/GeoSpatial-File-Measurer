import { useEffect, useMemo, useRef, useState } from 'react';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import NotFound from '@/pages/not-found';
import { Route, Switch, useLocation, Router as WouterRouter } from 'wouter';
import {
  Activity, AlertCircle, ArrowLeft, ArrowRight, Check, ChevronDown, CircleHelp,
  Clipboard, Clock3, Compass, FileArchive, FileCheck2, FileCode2, FileUp, Info, Layers3,
  LoaderCircle, Map, Ruler, Trash2, UploadCloud,
} from 'lucide-react';
import {
  getGetFileFeaturesQueryKey, getGetFileMeasurementsQueryKey, getGetFileQueryKey,
  getGetHealthQueryKey, getHealthCheckQueryKey, getListFilesQueryKey,
  useDeleteFile, useGetFile, useGetFileFeatures, useGetFileMeasurements, useGetHealth,
  useHealthCheck, useListFiles, useUploadFile,
} from '@workspace/api-client-react';
import type { FileList } from '@workspace/api-client-react';

const queryClient = new QueryClient();
const PAGE_SIZE = 20;
const fmt = (n: number | null | undefined, digits = 2) => n == null ? '—' : new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(n);
const pretty = (value?: string | null) => value ? value.replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : 'Unknown';
const dateLabel = (date: string) => new Date(date).toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
const errorText = (error: unknown) => {
  if (error && typeof error === 'object' && 'message' in error) return String(error.message);
  return 'The request could not be completed. Check the connection and try again.';
};

function Home() {
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState('');
  const [offset, setOffset] = useState(0);
  const [geometryFilter, setGeometryFilter] = useState('');
  const [expandedFeature, setExpandedFeature] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [copied, setCopied] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const healthCheck = useHealthCheck({ query: { queryKey: getHealthCheckQueryKey(), refetchInterval: 60000 } });
  const health = useGetHealth({ query: { queryKey: getGetHealthQueryKey(), refetchInterval: 60000 } });
  const listParams = useMemo(() => ({ limit: 8, offset: 0 }), []);
  const filesQuery = useListFiles(listParams, { query: { queryKey: getListFilesQueryKey(listParams) } });
  const files = filesQuery.data?.files ?? [];
  useEffect(() => {
    if (!selectedId && files.length) setSelectedId(files[0].id);
    if (selectedId && files.length && !files.some((f) => f.id === selectedId)) setSelectedId(files[0].id);
  }, [files, selectedId]);

  const fileQuery = useGetFile(selectedId, { query: { enabled: !!selectedId, queryKey: getGetFileQueryKey(selectedId) } });
  const measParams = useMemo(() => ({ limit: PAGE_SIZE, offset, ...(geometryFilter ? { geometry_type: geometryFilter } : {}) }), [offset, geometryFilter]);
  const measurementsQuery = useGetFileMeasurements(selectedId, measParams, { query: { enabled: !!selectedId, queryKey: getGetFileMeasurementsQueryKey(selectedId, measParams) } });
  const featureParams = useMemo(() => ({ limit: PAGE_SIZE, offset }), [offset]);
  const featuresQuery = useGetFileFeatures(selectedId, featureParams, { query: { enabled: !!selectedId, queryKey: getGetFileFeaturesQueryKey(selectedId, featureParams) } });
  const upload = useUploadFile();
  const remove = useDeleteFile();
  const info = fileQuery.data;
  const measurements = measurementsQuery.data;
  const rows = measurements?.features ?? [];
  const total = geometryFilter ? (measurements?.summary?.counts_by_geometry_type?.[geometryFilter] ?? measurements?.feature_count ?? 0) : (measurements?.feature_count ?? info?.feature_count ?? 0);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const distinctGeometryTypes = Object.keys(info?.geometry_type_counts ?? {});
  const healthStatus = health.data?.status ?? healthCheck.data?.status;
  const backendUp = !!healthStatus && !['down', 'error', 'unavailable', 'failed'].includes(healthStatus.toLowerCase());

  const handleUpload = (file?: File) => {
    if (!file) return;
    setUploadError('');
    const lower = file.name.toLowerCase();
    if (!(lower.endsWith('.kml') || lower.endsWith('.zip'))) {
      setUploadError('Choose a .kml file or a zipped Shapefile (.zip).');
      return;
    }
    upload.mutate({ data: { file } }, {
      onSuccess: async (uploaded) => {
        await Promise.all([
          qc.invalidateQueries({ queryKey: getListFilesQueryKey(listParams) }),
          qc.invalidateQueries({ queryKey: getListFilesQueryKey() }),
        ]);
        setSelectedId(uploaded.id);
        setOffset(0);
        setGeometryFilter('');
        setExpandedFeature(null);
        if (fileInput.current) fileInput.current.value = '';
      },
      onError: (err) => setUploadError(errorText(err)),
    });
  };
  const handleDelete = () => {
    if (!info || !window.confirm(`Delete ${info.filename}? This also removes its measurement records.`)) return;
    remove.mutate({ fileId: info.id }, {
      onSuccess: async () => {
        qc.setQueryData<FileList>(getListFilesQueryKey(listParams), (old) => old ? {
          ...old,
          files: old.files.filter((file) => file.id !== info.id),
          total: Math.max(0, old.total - 1),
        } : old);
        setSelectedId('');
        setOffset(0);
        await Promise.all([
          qc.invalidateQueries({ queryKey: getListFilesQueryKey(listParams) }),
          qc.invalidateQueries({ queryKey: getListFilesQueryKey() }),
          qc.invalidateQueries({ queryKey: getGetFileQueryKey(info.id) }),
          qc.invalidateQueries({ queryKey: getGetFileMeasurementsQueryKey(info.id) }),
          qc.invalidateQueries({ queryKey: getGetFileFeaturesQueryKey(info.id) }),
        ]);
      },
    });
  };
  const copyId = async () => {
    if (!info) return;
    try { await navigator.clipboard.writeText(info.id); setCopied(true); window.setTimeout(() => setCopied(false), 1600); } catch { setCopied(false); }
  };

  return (
    <div className="min-h-[100dvh] bg-background">
      <header className="flex h-[68px] items-center justify-between border-b border-border bg-card px-5 md:px-9">
        <div className="flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-primary text-primary-foreground"><Compass size={19} strokeWidth={2.2} /></div>
          <div className="leading-tight">
            <div className="text-[14px] font-extrabold tracking-[-.04em]">FIELDNOTE <span className="ml-1 font-mono text-[10px] font-medium tracking-[.15em] text-muted-foreground">MEASURE</span></div>
            <div className="mt-1 font-mono text-[9px] uppercase tracking-[.17em] text-muted-foreground">Geospatial review desk</div>
          </div>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-border bg-background px-3 py-1.5" data-testid="status-api">
          <span className={`h-1.5 w-1.5 rounded-full ${health.isLoading || healthCheck.isLoading ? 'animate-pulse bg-amber-500' : backendUp ? 'bg-emerald-600' : 'bg-rose-600'}`} />
          <span className="font-mono text-[10px] uppercase tracking-[.1em] text-muted-foreground">{health.isLoading || healthCheck.isLoading ? 'Checking API' : backendUp ? 'System operational' : 'API unavailable'}</span>
        </div>
      </header>

      <main className="mx-auto max-w-[1480px] px-4 pb-14 pt-7 md:px-9 md:pt-10">
        <section className="mb-8 flex flex-col justify-between gap-5 md:flex-row md:items-end">
          <div className="fade-up">
            <div className="mb-3 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[.18em] text-primary"><span className="h-px w-7 bg-primary" /> Survey tools / 01</div>
            <h1 className="text-[clamp(1.8rem,4vw,3rem)] font-extrabold leading-[1.05] tracking-[-.065em]">Measure with<br className="sm:hidden" /> <span className="text-primary">confidence.</span></h1>
            <p className="mt-3 max-w-[510px] text-sm leading-6 text-muted-foreground">Upload a field file. We’ll handle projection, geometry, and the math—so you can focus on the ground truth.</p>
          </div>
          <div className="flex items-center gap-3 border-l-2 border-accent pl-4 text-xs text-muted-foreground md:mb-1">
            <Ruler size={17} className="text-primary" />
            <span>Automatic projection selection<br /><b className="font-semibold text-foreground">Area in m² · distance in m</b></span>
          </div>
        </section>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_315px]">
          <div className="min-w-0 space-y-5">
            <section
              className={`relative overflow-hidden rounded-2xl border transition-colors duration-200 ${dragging ? 'border-primary bg-primary/5' : 'border-border bg-card'}`}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); handleUpload(e.dataTransfer.files?.[0]); }}
              data-testid="panel-upload"
            >
              <div className="absolute right-0 top-0 h-full w-[37%] overflow-hidden opacity-60 md:opacity-100"><div className="map-grid contour-lines absolute inset-0" /><svg className="absolute inset-0 h-full w-full" viewBox="0 0 420 220" fill="none" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><path d="M248 33L302 53L337 97L322 148L271 179L220 156L207 107L225 62L248 33Z" stroke="#176d68" strokeWidth="2"/><path d="M248 33L271 179M207 107L337 97M225 62L322 148" stroke="#176d68" strokeWidth="1" strokeDasharray="4 5"/><circle cx="271" cy="107" r="5" fill="#d5a94d"/><path d="M266 107h10m-5-5v10" stroke="#173d43" strokeWidth="1.5"/></svg></div>
              <div className="relative z-10 max-w-[720px] p-5 md:p-7">
                <div className="flex items-start justify-between">
                  <div><div className="flex items-center gap-2 text-sm font-bold"><FileUp size={17} className="text-primary" /> Add a source file</div><p className="mt-1.5 text-xs text-muted-foreground">KML or zipped Shapefile, processed right here.</p></div>
                  <span className="hidden rounded-md border border-border bg-background/80 px-2 py-1 font-mono text-[9px] uppercase tracking-wider text-muted-foreground sm:block">Step 01 / 02</span>
                </div>
                <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center">
                  <button onClick={() => fileInput.current?.click()} disabled={upload.isPending} data-testid="button-choose-file" className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-primary px-4 text-xs font-bold text-primary-foreground transition hover:-translate-y-0.5 hover:brightness-105 disabled:cursor-wait disabled:opacity-70">
                    {upload.isPending ? <LoaderCircle size={15} className="animate-spin" /> : <UploadCloud size={15} />}
                    {upload.isPending ? 'Processing file…' : 'Choose file'}
                  </button>
                  <span className="font-mono text-[10px] text-muted-foreground">or drop it here <span className="mx-1">·</span> .kml / .zip <span className="mx-1">·</span> up to 50 MB</span>
                  <input ref={fileInput} type="file" accept=".kml,.zip,application/vnd.google-earth.kml+xml,application/zip" className="hidden" data-testid="input-file-upload" onChange={(e) => handleUpload(e.target.files?.[0])} />
                </div>
                {uploadError && <div className="mt-3 flex items-center gap-2 text-xs font-semibold text-destructive" role="alert" data-testid="text-upload-error"><AlertCircle size={14} />{uploadError}</div>}
                {upload.isError && !uploadError && <div className="mt-3 flex items-center gap-2 text-xs text-destructive"><AlertCircle size={14} />Upload failed. Try again.</div>}
              </div>
            </section>

            {selectedId && (
              <section className="fade-up overflow-hidden rounded-2xl border border-border bg-card" data-testid="panel-file-details">
                {fileQuery.isLoading ? <PanelSkeleton /> : fileQuery.isError ? <QueryError label="Could not load this file." onRetry={() => fileQuery.refetch()} /> : info ? <>
                  <div className="flex flex-col justify-between gap-4 border-b border-border px-5 py-4 md:flex-row md:items-center md:px-6">
                    <div className="flex min-w-0 items-center gap-3">
                      <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-secondary text-primary">{info.file_type === 'kml' ? <FileCode2 size={19} /> : <FileArchive size={19} />}</div>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2"><h2 className="max-w-[380px] truncate text-sm font-extrabold tracking-[-.02em]" data-testid="text-filename">{info.filename}</h2><StatusBadge status={info.status} /></div>
                        <div className="mt-1 flex flex-wrap items-center gap-2 font-mono text-[9px] uppercase tracking-[.1em] text-muted-foreground"><span>{info.file_type}</span><span>·</span><span>{info.feature_count.toLocaleString()} features</span><span>·</span><button onClick={copyId} className="inline-flex items-center gap-1 hover:text-primary" data-testid="button-copy-file-id">{copied ? <Check size={10} /> : <Clipboard size={10} />}{copied ? 'Copied ID' : `ID ${info.id.slice(0, 8)}`}</button></div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 self-end md:self-auto">
                      <div className="rounded-lg bg-secondary/70 px-3 py-2 text-right"><div className="font-mono text-[8px] uppercase tracking-[.13em] text-muted-foreground">Source CRS</div><div className="mt-0.5 font-mono text-[10px] font-medium">{info.crs || 'Not provided'}</div></div>
                      <button onClick={handleDelete} disabled={remove.isPending} aria-label="Delete uploaded file" title="Delete file" data-testid="button-delete-file" className="grid h-9 w-9 place-items-center rounded-lg border border-border text-muted-foreground transition hover:border-destructive/40 hover:bg-destructive/5 hover:text-destructive disabled:opacity-50"><Trash2 size={15} /></button>
                    </div>
                  </div>
                  {info.error_message && <div className="mx-5 mt-4 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive md:mx-6" role="alert"><div className="flex gap-2"><AlertCircle size={15} className="shrink-0" /><span>{info.error_message}</span></div></div>}
                  {info.warnings?.length > 0 && <div className="mx-5 mt-3 rounded-lg border border-amber-700/15 bg-amber-500/5 p-3 text-xs text-foreground/80 md:mx-6"><div className="mb-1 flex items-center gap-2 font-bold"><Info size={13} className="text-amber-700" />Review notes</div>{info.warnings.map((warning, i) => <div key={i} className="ml-5 mt-1">{warning}</div>)}</div>}
                  <div className="grid grid-cols-2 border-b border-border md:grid-cols-4">
                    <Metric label="Total features" value={fmt(measurements?.summary?.counts_by_measurement_status ? Object.values(measurements.summary.counts_by_measurement_status).reduce((a, b) => a + b, 0) : info.feature_count, 0)} detail="in source file" icon={<Layers3 size={15} />} />
                    <Metric label="Total area" value={fmt(measurements?.summary?.total_area_sq_m)} unit="m²" detail={measurements?.summary ? `${fmt(measurements.summary.total_area_sq_m / 10000)} hectares` : 'Aggregated polygons'} icon={<Map size={15} />} />
                    <Metric label="Total length" value={fmt(measurements?.summary?.total_length_m)} unit="m" detail="lines & boundaries" icon={<Ruler size={15} />} />
                    <Metric label="Projection" value={measurements?.crs || info.crs || '—'} detail={measurements?.crs ? 'measurement CRS' : 'source reference'} icon={<Compass size={15} />} compact />
                  </div>
                  <div className="px-5 py-4 md:px-6">
                    <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                      <div><h3 className="text-sm font-extrabold tracking-[-.02em]">Feature measurements</h3><p className="mt-1 text-[11px] text-muted-foreground">Calculated per geometry, with the method recorded.</p></div>
                      <label className="relative flex h-9 min-w-[170px] items-center rounded-lg border border-border bg-background px-3 text-xs" data-testid="field-geometry-filter">
                        <span className="mr-2 text-muted-foreground">Type</span>
                        <select value={geometryFilter} onChange={(e) => { setGeometryFilter(e.target.value); setOffset(0); setExpandedFeature(null); }} className="h-full min-w-0 flex-1 appearance-none bg-transparent pr-5 text-xs font-semibold outline-none" aria-label="Filter by geometry type" data-testid="select-geometry-type">
                          <option value="">All geometry</option>{distinctGeometryTypes.map((type) => <option key={type} value={type}>{pretty(type)}</option>)}
                        </select><ChevronDown size={13} className="pointer-events-none absolute right-3 text-muted-foreground" />
                      </label>
                    </div>
                    {measurementsQuery.isLoading ? <RowsSkeleton /> : measurementsQuery.isError ? <QueryError label="Measurements could not be loaded." onRetry={() => measurementsQuery.refetch()} /> : rows.length ? <>
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[690px] border-collapse text-left">
                          <thead><tr className="border-y border-border bg-background font-mono text-[9px] uppercase tracking-[.12em] text-muted-foreground"><th className="px-3 py-2.5 font-medium">Feature</th><th className="px-3 py-2.5 font-medium">Geometry</th><th className="px-3 py-2.5 font-medium">Area</th><th className="px-3 py-2.5 font-medium">Length</th><th className="px-3 py-2.5 font-medium">Status / method</th><th className="w-8 px-2 py-2.5" /></tr></thead>
                          <tbody>
                            {rows.map((row) => {
                              const extra = featuresQuery.data?.features?.find((f) => f.feature_index === row.feature_index);
                              const isOpen = expandedFeature === row.feature_index;
                              return <FragmentRow key={row.feature_index} row={row} extra={extra} isOpen={isOpen} onToggle={() => setExpandedFeature(isOpen ? null : row.feature_index)} />;
                            })}
                          </tbody>
                        </table>
                      </div>
                      <div className="mt-3 flex items-center justify-between gap-2">
                        <span className="font-mono text-[10px] text-muted-foreground">{offset + 1}–{Math.min(offset + rows.length, total)} <span className="mx-1">/</span> {total.toLocaleString()} features</span>
                        <div className="flex items-center gap-1.5"><button onClick={() => { setOffset(Math.max(0, offset - PAGE_SIZE)); setExpandedFeature(null); }} disabled={offset === 0} className="grid h-8 w-8 place-items-center rounded-md border border-border transition hover:bg-secondary disabled:opacity-35" aria-label="Previous page" data-testid="button-prev-page"><ArrowLeft size={14} /></button><span className="px-1 font-mono text-[10px] text-muted-foreground">{currentPage} / {totalPages}</span><button onClick={() => { setOffset(offset + PAGE_SIZE); setExpandedFeature(null); }} disabled={offset + PAGE_SIZE >= total} className="grid h-8 w-8 place-items-center rounded-md border border-border transition hover:bg-secondary disabled:opacity-35" aria-label="Next page" data-testid="button-next-page"><ArrowRight size={14} /></button></div>
                      </div>
                    </> : <div className="rounded-xl border border-dashed border-border bg-background/70 px-5 py-10 text-center"><div className="mx-auto grid h-10 w-10 place-items-center rounded-full bg-secondary text-muted-foreground"><Ruler size={17} /></div><p className="mt-3 text-xs font-bold">{geometryFilter ? 'No features match this geometry.' : 'No measurements available.'}</p><p className="mt-1 text-[11px] text-muted-foreground">{geometryFilter ? 'Choose another geometry type or view all.' : 'The file may be empty or still processing.'}</p>{geometryFilter && <button onClick={() => setGeometryFilter('')} className="mt-3 text-[11px] font-bold text-primary underline underline-offset-4">Clear filter</button>}</div>}
                  </div>
                </> : <div className="p-6 text-sm text-muted-foreground">Select an upload to inspect its measurements.</div>}
              </section>
            )}

            {!selectedId && !filesQuery.isLoading && (
              <section className="map-grid relative overflow-hidden rounded-2xl border border-border px-6 py-12 text-center md:py-16" data-testid="empty-inspection">
                <div className="contour-lines absolute inset-0 opacity-50" />
                <div className="relative mx-auto max-w-md">
                  <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl border border-primary/20 bg-card text-primary shadow-sm"><Map size={21} /></div>
                  <p className="mt-4 font-mono text-[9px] uppercase tracking-[.17em] text-primary">Your review desk</p>
                  <h2 className="mt-2 text-xl font-extrabold tracking-[-.04em]">No file selected</h2>
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">Upload KML or a zipped Shapefile above to inspect accurate area and length measurements.</p>
                </div>
              </section>
            )}
          </div>

          <aside className="space-y-5">
            <section className="overflow-hidden rounded-2xl border border-border bg-card" data-testid="panel-recent-files">
              <div className="flex items-center justify-between border-b border-border px-4 py-4">
                <div><h2 className="text-xs font-extrabold tracking-[-.01em]">Recent uploads</h2><p className="mt-1 font-mono text-[9px] uppercase tracking-[.12em] text-muted-foreground">Latest field files</p></div>
                <Clock3 size={16} className="text-primary" />
              </div>
              {filesQuery.isLoading ? <div className="space-y-2 p-4">{[0,1,2].map((n) => <div key={n} className="h-[58px] animate-pulse rounded-lg bg-muted" />)}</div>
                : filesQuery.isError ? <div className="p-4"><QueryError label="Upload history is unavailable." onRetry={() => filesQuery.refetch()} /></div>
                : files.length ? <div className="p-2">
                  {files.map((file) => <div key={file.id} className={`group flex w-full items-center gap-3 rounded-xl px-2.5 py-3 text-left transition-colors ${selectedId === file.id ? 'bg-primary/8 ring-1 ring-primary/20' : 'hover:bg-secondary/60'}`}>
                    <button onClick={() => { setSelectedId(file.id); setOffset(0); setGeometryFilter(''); setExpandedFeature(null); }} data-testid={`button-select-file-${file.id}`} className="flex min-w-0 flex-1 items-center gap-3 text-left">
                      <div className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg ${selectedId === file.id ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground'}`}>{file.file_type === 'kml' ? <FileCode2 size={15} /> : <FileArchive size={15} />}</div>
                      <div className="min-w-0 flex-1"><div className="truncate text-[11px] font-bold">{file.filename}</div><div className="mt-1 flex items-center gap-1.5 font-mono text-[9px] text-muted-foreground"><span>{file.feature_count} features</span><span>·</span><span>{new Date(file.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span></div></div>
                      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${file.status === 'COMPLETED' ? 'bg-emerald-600' : file.status === 'FAILED' ? 'bg-rose-600' : 'bg-amber-500'}`} />
                    </button>
                  </div>)}
                  {(filesQuery.data?.total ?? 0) > files.length && <div className="border-t border-border px-3 py-3 text-center font-mono text-[9px] text-muted-foreground">{files.length} of {filesQuery.data?.total} uploads shown</div>}
                </div>
                : <div className="px-5 py-9 text-center"><div className="mx-auto grid h-9 w-9 place-items-center rounded-full bg-secondary text-muted-foreground"><FileCheck2 size={16} /></div><p className="mt-3 text-xs font-bold">No uploads yet</p><p className="mt-1 text-[10px] leading-4 text-muted-foreground">Your processed files will appear here.</p></div>}
            </section>

            {info && (
              <section className="overflow-hidden rounded-2xl border border-border bg-card" data-testid="panel-file-metadata">
                <div className="flex items-center justify-between border-b border-border px-4 py-4"><div><h2 className="text-xs font-extrabold">Source details</h2><p className="mt-1 font-mono text-[9px] uppercase tracking-[.12em] text-muted-foreground">File metadata</p></div><Info size={15} className="text-primary" /></div>
                <dl className="space-y-0 px-4">
                  <Meta label="Imported" value={dateLabel(info.created_at)} />
                  <Meta label="Coordinate system" value={info.crs || 'Not declared'} />
                  <Meta label="Geometry types" value={Object.entries(info.geometry_type_counts ?? {}).map(([type, count]) => `${pretty(type)} ${count}`).join(' · ') || '—'} />
                  <Meta label="Measurement CRS" value={measurements?.crs || 'Calculated on request'} last />
                </dl>
                <div className="mx-4 mb-4 flex items-start gap-2 rounded-lg bg-secondary/60 p-3 text-[10px] leading-4 text-muted-foreground"><CircleHelp size={13} className="mt-0.5 shrink-0 text-primary" /><span>Area and length are calculated using an appropriate projected CRS. Each result includes its projection and method.</span></div>
              </section>
            )}
            <div className="rounded-xl border border-border bg-background/70 p-4">
              <div className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[.15em] text-muted-foreground"><Activity size={13} className="text-primary" />Measurement protocol</div>
              <div className="mt-3 space-y-2 text-[10px] leading-4 text-muted-foreground"><p className="flex gap-2"><Check size={12} className="mt-0.5 shrink-0 text-primary" />Projection-aware measurements</p><p className="flex gap-2"><Check size={12} className="mt-0.5 shrink-0 text-primary" />Source CRS stays on record</p><p className="flex gap-2"><Check size={12} className="mt-0.5 shrink-0 text-primary" />Per-feature method notes</p></div>
            </div>
          </aside>
        </div>
        <footer className="mt-8 flex flex-col justify-between gap-2 border-t border-border pt-4 font-mono text-[9px] uppercase tracking-[.1em] text-muted-foreground sm:flex-row"><span>Fieldnote / Measurement utility</span><span>Source coordinates preserved · Units shown explicitly</span></footer>
      </main>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = { COMPLETED: 'bg-emerald-700/10 text-emerald-800', PROCESSING: 'bg-amber-600/10 text-amber-800', PENDING: 'bg-amber-600/10 text-amber-800', FAILED: 'bg-destructive/10 text-destructive' };
  return <span className={`rounded-full px-2 py-1 font-mono text-[8px] uppercase tracking-[.1em] ${styles[status] || 'bg-secondary text-muted-foreground'}`} data-testid="status-file">{status}</span>;
}
function Metric({ label, value, unit, detail, icon, compact }: { label: string; value: string; unit?: string; detail: string; icon: React.ReactNode; compact?: boolean }) {
  return <div className="min-w-0 border-b border-r border-border px-4 py-4 last:border-r-0 md:border-b-0 md:px-5"><div className="flex items-center justify-between gap-2"><span className="font-mono text-[9px] uppercase tracking-[.12em] text-muted-foreground">{label}</span><span className="text-primary">{icon}</span></div><div className={`mt-2 truncate font-extrabold tracking-[-.04em] ${compact ? 'text-sm' : 'text-[clamp(1.05rem,2vw,1.45rem)]'}`} data-testid={`metric-${label.toLowerCase().replaceAll(' ', '-')}`}>{value}<span className="ml-1 text-[10px] font-semibold tracking-normal text-muted-foreground">{unit}</span></div><div className="mt-1 truncate text-[9px] text-muted-foreground">{detail}</div></div>;
}
function Meta({ label, value, last }: { label: string; value: string; last?: boolean }) {
  return <div className={`flex justify-between gap-3 py-3 ${last ? '' : 'border-b border-border'}`}><dt className="text-[10px] text-muted-foreground">{label}</dt><dd className="max-w-[58%] break-words text-right font-mono text-[9px] text-foreground">{value}</dd></div>;
}
function QueryError({ label, onRetry }: { label: string; onRetry: () => void }) {
  return <div className="flex items-center justify-between gap-3 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-[11px] text-destructive" role="alert"><span className="flex items-center gap-2"><AlertCircle size={14} />{label}</span><button onClick={onRetry} className="shrink-0 rounded-md border border-destructive/20 px-2 py-1 font-bold hover:bg-destructive/10" data-testid="button-retry">Retry</button></div>;
}
function PanelSkeleton() {
  return <div className="animate-pulse p-5"><div className="h-10 w-2/3 rounded-lg bg-muted" /><div className="mt-5 grid grid-cols-2 gap-2 md:grid-cols-4">{[0,1,2,3].map((n) => <div key={n} className="h-20 rounded-lg bg-muted" />)}</div><div className="mt-5 h-40 rounded-lg bg-muted" /></div>;
}
function RowsSkeleton() {
  return <div className="space-y-2 py-2" aria-label="Loading measurements">{[0,1,2,3].map((n) => <div key={n} className="h-10 animate-pulse rounded-md bg-muted/70" />)}</div>;
}
function FragmentRow({ row, extra, isOpen, onToggle }: { row: any; extra: any; isOpen: boolean; onToggle: () => void }) {
  const area = row.measurements?.area_sq_m;
  const length = row.measurements?.length_m;
  const tone = row.measurement_status === 'CALCULATED' ? 'text-emerald-700' : row.measurement_status === 'ERROR' ? 'text-destructive' : 'text-muted-foreground';
  return <>
    <tr className="border-b border-border/70 transition-colors hover:bg-secondary/35" data-testid={`row-measurement-${row.feature_index}`}>
      <td className="px-3 py-3 font-mono text-[10px] font-medium">#{row.feature_index}</td>
      <td className="px-3 py-3"><div className="text-[10px] font-semibold">{pretty(row.geometry_type)}</div>{row.layer && <div className="mt-0.5 max-w-[110px] truncate text-[9px] text-muted-foreground">{row.layer}</div>}</td>
      <td className="px-3 py-3 font-mono text-[10px]">{area == null ? '—' : <>{fmt(area)}<span className="ml-1 text-[8px] text-muted-foreground">m²</span></>}</td>
      <td className="px-3 py-3 font-mono text-[10px]">{length == null ? '—' : <>{fmt(length)}<span className="ml-1 text-[8px] text-muted-foreground">m</span></>}</td>
      <td className="px-3 py-3"><span className={`font-mono text-[9px] font-medium ${tone}`}>{pretty(row.measurement_status)}</span><div className="mt-0.5 max-w-[190px] truncate text-[8px] text-muted-foreground">{row.method || row.note || row.projected_crs || '—'}</div></td>
      <td className="px-2 py-3"><button onClick={onToggle} aria-label={isOpen ? 'Hide feature metadata' : 'Show feature metadata'} className={`grid h-7 w-7 place-items-center rounded-md transition hover:bg-secondary ${isOpen ? 'bg-secondary text-primary' : 'text-muted-foreground'}`} data-testid={`button-feature-details-${row.feature_index}`}><ChevronDown size={13} className={`transition-transform ${isOpen ? 'rotate-180' : ''}`} /></button></td>
    </tr>
    {isOpen && <tr className="border-b border-border bg-background/70"><td colSpan={6} className="px-4 py-3"><div className="grid gap-4 md:grid-cols-[1fr_1.4fr]">
      <div><div className="mb-1 font-mono text-[8px] uppercase tracking-[.13em] text-muted-foreground">Calculation record</div><div className="space-y-1 text-[10px]"><p><span className="text-muted-foreground">Projected CRS </span><span className="font-mono">{row.projected_crs || '—'}</span></p><p><span className="text-muted-foreground">Method </span>{row.method || '—'}</p>{row.note && <p className="text-amber-800">{row.note}</p>}</div></div>
      <div><div className="mb-1 font-mono text-[8px] uppercase tracking-[.13em] text-muted-foreground">Feature properties</div>{extra ? <pre className="max-h-36 overflow-auto rounded-md bg-secondary/60 p-2 font-mono text-[9px] leading-4">{JSON.stringify(extra.properties, null, 2)}</pre> : <div className="text-[10px] text-muted-foreground">{featuresLoadingText(row.feature_index)}</div>}</div>
    </div></td></tr>}
  </>;
}
function featuresLoadingText(index: number) {
  return index < 0 ? 'No feature metadata available.' : 'Metadata is loading or not available for this page.';
}

function Router() {
  return <RoutedErrorBoundary><Switch><Route path="/" component={Home} /><Route component={NotFound} /></Switch></RoutedErrorBoundary>;
}
function RoutedErrorBoundary({ children }: { children: React.ReactNode }) {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}>{children}</ErrorBoundary>;
}
function App() {
  return <QueryClientProvider client={queryClient}><TooltipProvider><WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}><Router /></WouterRouter><Toaster /></TooltipProvider></QueryClientProvider>;
}
export default App;
