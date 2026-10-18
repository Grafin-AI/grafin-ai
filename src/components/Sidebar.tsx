import type { ReactNode } from 'react';
import gardaLogo from 'figma:asset/db1da7b05c661826c500feb1fd5509a19ea8cfd0.png';
import { Activity, BarChart3, Radar, UserCheck } from 'lucide-react';
import { useFraudAnalytics, useSystemHealth } from '../api/queries';
import { formatScore } from '../lib/format';
import { cn } from './ui/utils';

export interface NavItem {
  title: string;
  icon: ReactNode;
  href: string;
}

export const navigationItems: NavItem[] = [
  { title: 'Monitoring', icon: <Activity className="size-[18px]" aria-hidden />, href: '/dashboard' },
  { title: 'Radar Regulator', icon: <Radar className="size-[18px]" aria-hidden />, href: '/radar' },
  { title: 'Profil Risiko', icon: <UserCheck className="size-[18px]" aria-hidden />, href: '/user-risk-profiling' },
  { title: 'Analitik', icon: <BarChart3 className="size-[18px]" aria-hidden />, href: '/analytics' },
];

interface SidebarProps {
  currentView?: string;
  onNavigate?: (view: string) => void;
  /** Rendered at the bottom of the rail (the active-model card in the app). */
  footer?: ReactNode;
}

export function Sidebar({ currentView = '/dashboard', onNavigate, footer }: SidebarProps) {
  return (
    <aside
      className="w-full shrink-0 border-b border-border bg-sidebar px-4 py-4 lg:sticky lg:top-0 lg:flex lg:h-screen lg:w-60 lg:flex-col lg:gap-7 lg:border-b-0 lg:border-r lg:py-6"
    >
      <div className="flex flex-col items-start gap-2">
        <img src={gardaLogo} alt="Garda AI" className="h-8 w-auto max-w-full object-contain" />
        <p className="text-xs text-muted-foreground">Fraud &amp; Anomaly Detection Platform</p>
      </div>

      <nav aria-label="Navigasi utama" className="mt-4 lg:mt-0">
        <ul className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
          {navigationItems.map((item) => {
            const active = currentView === item.href;
            return (
              <li key={item.href} className="shrink-0">
                <button
                  type="button"
                  onClick={() => onNavigate?.(item.href)}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    'flex min-h-11 w-full items-center gap-2.5 rounded-lg px-3 text-left text-sm transition-colors',
                    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
                    active
                      ? 'bg-brand-soft font-medium text-[#0B6FB8]'
                      : 'text-text-secondary hover:bg-accent hover:text-foreground',
                  )}
                >
                  {item.icon}
                  <span className="whitespace-nowrap">{item.title}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {footer && <div className="mt-auto hidden lg:block">{footer}</div>}
    </aside>
  );
}

/** Active scoring model card for the bottom of the sidebar. Every value comes from the API. */
export function ActiveModelCard() {
  const { data: health, isLoading } = useSystemHealth();
  const { data: analytics } = useFraudAnalytics();
  const f1 = analytics?.detection?.f1;
  const services = health ? [
    { label: 'Database', ok: health.db_ok },
    { label: 'Redis', ok: health.redis_ok },
  ] : [];

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3.5" aria-live="polite">
      <span className="text-xs text-muted-foreground">Model aktif</span>
      <span className="text-sm font-semibold text-foreground break-words">
        {isLoading ? 'Memuat…' : health?.model_name ?? (health?.model_accuracy_simulated ? 'Simulasi label-replay' : '—')}
      </span>
      {f1 != null && (
        <div className="flex justify-between text-xs">
          <span className="text-muted-foreground">F1 deteksi</span>
          <span className="num text-approved">{formatScore(f1, 3)}</span>
        </div>
      )}
      {services.length > 0 && (
        <div className="flex flex-wrap gap-x-3 gap-y-1 border-t border-border pt-2 text-xs text-muted-foreground">
          {services.map((s) => (
            <span key={s.label} className="inline-flex items-center gap-1.5">
              <span aria-hidden className={cn('size-1.5 rounded-full', s.ok ? 'bg-approved' : 'bg-blocked')} />
              {s.label} {s.ok ? 'online' : 'offline'}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
