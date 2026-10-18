import { Component, Suspense, lazy, useRef, useState, type ComponentType, type ReactNode } from 'react';
import { ActiveModelCard, Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { MetricsOverview } from './components/MetricsOverview';
import { TransactionVolume } from './components/TransactionVolume';
import { TransactionHeatmap } from './components/TransactionHeatmap';
import { TransactionMonitor } from './components/TransactionMonitor';
import { FraudAnalytics, TypologyBars } from './components/FraudAnalytics';
import { GeographicMap } from './components/GeographicMap';
import { AlertsPanel } from './components/AlertsPanel';
import { UserRiskProfiling } from './components/UserRiskProfiling';
import { useSystemHealth } from './api/queries';
import { Skeleton } from './components/ui/skeleton';
import { cn } from './components/ui/utils';
import { formatTime } from './lib/formatTime';
import { formatInt } from './lib/format';
import { usePageFade, useStaggerIn } from './lib/motion';

// ── Regulator radar (owned by another module) ────────────────────────────────
// Resolved through import.meta.glob so the bundle builds whether or not the
// module exists yet, and is code-split either way. Accepts a default or a
// named `RegulatorRadar` export.
type RadarModule = { default?: ComponentType; RegulatorRadar?: ComponentType };
const radarLoader = import.meta.glob<RadarModule>('./components/RegulatorRadar.tsx')['./components/RegulatorRadar.tsx'];

function RadarUnavailable() {
  return <EmptyState title="Radar Regulator belum tersedia" body="Modul radar sedang disiapkan." />;
}

const RegulatorRadar = lazy(async () => {
  if (!radarLoader) return { default: RadarUnavailable };
  const m = await radarLoader();
  return { default: m.default ?? m.RegulatorRadar ?? RadarUnavailable };
});

class ViewBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <EmptyState title="Tampilan gagal dimuat" body="Muat ulang halaman untuk mencoba lagi." />;
    return this.props.children;
  }
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="grid h-96 place-items-center rounded-xl border border-border bg-card">
      <div className="text-center">
        <h2 className="text-lg font-semibold text-foreground">{title}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{body}</p>
      </div>
    </div>
  );
}

// ── System health ────────────────────────────────────────────────────────────
function HealthCard({ title, status, statusClass, bar, barClass, note }: {
  title: string; status: ReactNode; statusClass: string; bar: number; barClass: string; note: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-foreground">{title}</span>
        <span className={cn('text-sm', statusClass)}>{status}</span>
      </div>
      <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-surface-inset" aria-hidden>
        <div className={cn('h-2 rounded-full', barClass)} style={{ width: `${bar}%` }} />
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">{note}</p>
    </div>
  );
}

export function SystemHealthCards() {
  const { data, isLoading } = useSystemHealth();

  if (isLoading) {
    return (
      <div className="grid gap-3">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-20 w-full" />)}
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      <HealthCard
        title="Database"
        status={data?.db_ok ? 'Online' : 'Offline'}
        statusClass={data?.db_ok ? 'text-approved' : 'text-blocked'}
        bar={data?.db_ok ? 100 : 10}
        barClass={data?.db_ok ? 'bg-approved' : 'bg-blocked'}
        note={data?.db_ok ? 'Koneksi database sehat' : 'Database tidak dapat dijangkau'}
      />
      <HealthCard
        title="Model Accuracy"
        status={data?.model_name ? `Model: ${data.model_name}` : data?.model_accuracy_simulated ? 'Simulated (Phase 1)' : '—'}
        statusClass={data?.model_name ? 'text-approved' : data?.model_accuracy_simulated ? 'text-flagged' : 'text-muted-foreground'}
        bar={data?.model_name ? 100 : data?.model_accuracy_simulated ? 60 : 0}
        barClass={data?.model_name ? 'bg-approved' : 'bg-flagged'}
        note={data?.model_name
          ? 'Penilaian model aktif'
          : data?.model_accuracy_simulated
            ? 'Label-replay simulation active — accuracy not yet measured'
            : 'Belum ada data akurasi model'}
      />
      <HealthCard
        title="Cache (Redis)"
        status={data?.redis_ok ? 'Online' : 'Offline'}
        statusClass={data?.redis_ok ? 'text-approved' : 'text-blocked'}
        bar={data?.redis_ok ? 100 : 10}
        barClass={data?.redis_ok ? 'bg-approved' : 'bg-blocked'}
        note={data?.redis_ok ? 'Cache Redis beroperasi' : 'Redis tidak tersedia'}
      />
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-foreground">Events Surfaced</span>
          <span className="num text-sm text-link">
            {data?.events_surfaced != null ? formatInt(data.events_surfaced) : '—'}
          </span>
        </div>
        <p className="mt-1.5 text-xs text-muted-foreground">Total event yang diproses sistem</p>
      </div>
    </div>
  );
}

// ── Views ────────────────────────────────────────────────────────────────────
const VIEWS: Record<string, { title: string; subtitle: string }> = {
  '/dashboard': { title: 'Monitoring Transaksi', subtitle: 'Pemantauan real-time BI-FAST, QRIS, transfer antarbank' },
  '/radar': { title: 'Radar Regulator', subtitle: 'Pandangan lintas institusi untuk pengawasan OJK/BI' },
  '/user-risk-profiling': { title: 'Profil Risiko', subtitle: 'Skor risiko nasabah dan entitas dari model' },
  '/analytics': { title: 'Analitik', subtitle: 'Kinerja deteksi, pola tipologi, sebaran wilayah dan kesehatan sistem' },
};

function SectionTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="mb-3">
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      <p className="mt-0.5 text-sm text-muted-foreground">{subtitle}</p>
    </div>
  );
}

function MonitoringView({ onLatestEventTime }: { onLatestEventTime: (iso: string | null) => void }) {
  return (
    <>
      <MetricsOverview />
      <div className="grid items-start gap-4 xl:grid-cols-3">
        <div className="min-w-0 xl:col-span-2">
          <TransactionMonitor onLatestEventTime={onLatestEventTime} />
        </div>
        <AlertsPanel />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <TypologyBars />
        <TransactionVolume />
      </div>
    </>
  );
}

function AnalyticsView() {
  return (
    <>
      <FraudAnalytics />
      <div data-animate className="min-w-0">
        <TransactionHeatmap />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div data-animate className="min-w-0">
          <SectionTitle title="Sebaran Wilayah" subtitle="Distribusi fraud per provinsi" />
          <GeographicMap />
        </div>
        <div data-animate className="min-w-0">
          <SectionTitle title="Kesehatan Sistem" subtitle="Status layanan dan model secara real-time" />
          <SystemHealthCards />
        </div>
      </div>
    </>
  );
}

export default function App() {
  const [currentView, setCurrentView] = useState('/dashboard');
  const [latestEventTime, setLatestEventTime] = useState<string | null>(null);
  const viewRef = useRef<HTMLDivElement>(null);
  usePageFade(viewRef, currentView);
  useStaggerIn(viewRef, [currentView]);

  const meta = VIEWS[currentView] ?? VIEWS['/dashboard'];

  return (
    <div className="min-h-screen bg-background text-foreground lg:flex">
      <Sidebar currentView={currentView} onNavigate={setCurrentView} footer={<ActiveModelCard />} />

      <main className="flex min-w-0 flex-1 flex-col gap-5 px-4 pb-10 pt-6 sm:px-7">
        <Header
          title={meta.title}
          subtitle={meta.subtitle}
          liveTime={currentView === '/dashboard' && latestEventTime ? formatTime(latestEventTime) : null}
        />

        <div ref={viewRef} key={currentView} className="flex flex-col gap-5">
          {currentView === '/dashboard' ? (
            <MonitoringView onLatestEventTime={setLatestEventTime} />
          ) : currentView === '/radar' ? (
            <ViewBoundary>
              <Suspense fallback={<Skeleton className="h-96 w-full rounded-xl" />}>
                <RegulatorRadar />
              </Suspense>
            </ViewBoundary>
          ) : currentView === '/user-risk-profiling' ? (
            <UserRiskProfiling />
          ) : currentView === '/analytics' ? (
            <AnalyticsView />
          ) : (
            <EmptyState title="Halaman Sedang Dibangun" body="Fitur ini akan segera tersedia" />
          )}
        </div>
      </main>
    </div>
  );
}
