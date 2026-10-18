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

// ── System health (compact strip, last on the dashboard) ─────────────────────
function HealthItem({ ok, tone, children }: { ok?: boolean; tone?: 'ok' | 'warn' | 'bad' | 'idle'; children: ReactNode }) {
  const t = tone ?? (ok ? 'ok' : 'bad');
  const dot = t === 'ok' ? 'bg-approved' : t === 'warn' ? 'bg-flagged' : t === 'bad' ? 'bg-blocked' : 'bg-text-faint';
  return (
    <span className="inline-flex items-center gap-2 text-[13px] text-text-secondary">
      <span aria-hidden className={cn('size-2 shrink-0 rounded-full', dot)} />
      {children}
    </span>
  );
}

export function SystemHealthCards() {
  const { data, isLoading } = useSystemHealth();

  return (
    <section aria-label="Kesehatan sistem" data-animate className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border border-border bg-card px-[18px] py-3.5">
      <h2 className="text-[15px] font-semibold text-foreground">Kesehatan Sistem</h2>
      {isLoading ? (
        <Skeleton className="h-4 w-80" />
      ) : (
        <>
          <HealthItem ok={!!data?.db_ok}>{data?.db_ok ? 'Database sehat' : 'Database tidak terjangkau'}</HealthItem>
          <HealthItem ok={!!data?.redis_ok}>{data?.redis_ok ? 'Redis sehat' : 'Redis tidak tersedia'}</HealthItem>
          {data?.model_name ? (
            <HealthItem tone="ok">Model: {data.model_name}</HealthItem>
          ) : data?.model_accuracy_simulated ? (
            <HealthItem tone="warn">
              <span>Simulated (Phase 1)</span>
              <span className="text-xs text-muted-foreground">Label-replay simulation active — accuracy not yet measured</span>
            </HealthItem>
          ) : (
            <HealthItem tone="idle">Model: —</HealthItem>
          )}
          <span className="text-[13px] text-text-secondary">
            Event diproses{' '}
            <span className="num font-medium text-foreground">
              {data?.events_surfaced != null ? formatInt(data.events_surfaced) : '—'}
            </span>
          </span>
        </>
      )}
    </section>
  );
}

// ── Views ────────────────────────────────────────────────────────────────────
const VIEWS: Record<string, { title: string; subtitle: string }> = {
  '/dashboard': { title: 'Monitoring Transaksi', subtitle: 'Pemantauan real-time BI-FAST, QRIS, transfer antarbank' },
  '/radar': { title: 'Radar Regulator', subtitle: 'Pandangan lintas institusi untuk BI / OJK — aliran dana mencurigakan antar bank' },
  '/user-risk-profiling': { title: 'Profil Risiko', subtitle: 'Skor risiko nasabah dan entitas dari model' },
  '/analytics': { title: 'Analitik', subtitle: 'Kinerja deteksi model dan nominal per tipologi' },
};

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
      <div className="grid items-stretch gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <TransactionVolume />
        <TransactionHeatmap />
      </div>
      <div className="grid items-start gap-4 lg:grid-cols-2">
        <TypologyBars />
        <GeographicMap />
      </div>
      <SystemHealthCards />
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
            <FraudAnalytics />
          ) : (
            <EmptyState title="Halaman Sedang Dibangun" body="Fitur ini akan segera tersedia" />
          )}
        </div>
      </main>
    </div>
  );
}
