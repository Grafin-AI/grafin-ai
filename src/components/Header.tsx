import { Bell, Search } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';

interface HeaderProps {
  title?: string;
  subtitle?: string;
  /** Dataset time of the newest live event, already formatted; shown in the LIVE badge. */
  liveTime?: string | null;
}

export function Header({
  title = 'Monitoring Transaksi',
  subtitle = 'Pemantauan real-time BI-FAST, QRIS, transfer antarbank',
  liveTime,
}: HeaderProps) {
  const { user } = useAuth();
  const initials = (user?.email ?? '?').slice(0, 2).toUpperCase();

  return (
    <header className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="text-2xl font-semibold text-foreground">{title}</h1>
        <p className="text-sm text-muted-foreground">{subtitle}</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <span
          className="inline-flex items-center gap-2 rounded-full bg-approved-bg px-3 py-1.5 text-[13px] font-medium text-[#5BE3B5]"
          role="status"
        >
          <span aria-hidden className="relative flex size-2">
            <span className="absolute inline-flex size-full rounded-full bg-approved opacity-60 motion-safe:animate-ping" />
            <span className="relative inline-flex size-2 rounded-full bg-approved" />
          </span>
          LIVE{liveTime ? <span className="num">· {liveTime}</span> : null}
        </span>

        <label className="flex h-11 items-center gap-2 rounded-lg border border-border-strong bg-card px-3 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring">
          <Search className="size-4 text-muted-foreground" aria-hidden />
          <span className="sr-only">Cari transaksi</span>
          <input
            type="search"
            placeholder="Cari ID / rekening"
            className="w-44 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
          />
        </label>

        <button
          type="button"
          aria-label="Notifikasi"
          className="grid size-11 place-items-center rounded-lg border border-border-strong bg-card text-foreground transition-colors hover:bg-accent"
        >
          <Bell className="size-[18px]" aria-hidden />
        </button>

        <div className="flex items-center gap-2">
          <span aria-hidden className="grid size-8 place-items-center rounded-full bg-brand-soft text-[13px] font-semibold text-foreground">
            {initials}
          </span>
          <div className="flex flex-col leading-tight">
            <span className="text-sm text-foreground">{user?.email ?? '—'}</span>
            <span className="text-xs capitalize text-muted-foreground">{user?.role ?? ''}</span>
          </div>
        </div>
      </div>
    </header>
  );
}
