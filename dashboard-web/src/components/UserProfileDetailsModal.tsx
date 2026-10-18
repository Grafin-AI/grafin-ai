import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { ScrollArea } from './ui/scroll-area';
import { Skeleton } from './ui/skeleton';
import { cn } from './ui/utils';
import { AlertTriangle, Flag, MapPin, Shield, User as UserIcon } from 'lucide-react';
import { useUserProfile } from '../api/queries';
import { formatIDR, formatInt, formatPct } from '../lib/format';
import { riskMeta } from '../lib/status';

interface UserProfileDetailsModalProps {
  entityId: string | null;
  isOpen: boolean;
  onClose: () => void;
}

// Qualitative follow-up per stored risk level. Deliberately no figures: every
// number in this dialog comes from the profile API.
const RECOMMENDATION: Record<string, string> = {
  High: 'Prioritas tinggi: lakukan enhanced due diligence, tinjau riwayat transaksi dan sumber dana, dan pertimbangkan pelaporan LTKM ke PPATK bila indikasi terkonfirmasi.',
  Medium: 'Pantau ketat: tetapkan peringatan untuk transaksi bernilai besar dan eskalasikan ke tinjauan manual bila skor risiko atau jumlah transaksi ditandai meningkat.',
  Low: 'Proses normal: lanjutkan pemantauan standar dan tinjauan berkala.',
};

const PANEL = 'rounded-xl border border-border bg-card-2 p-4';

function Stat({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn('num text-xl font-semibold text-foreground', className)}>{value}</span>
    </div>
  );
}

export function UserProfileDetailsModal({ entityId, isOpen, onClose }: UserProfileDetailsModalProps) {
  const { data: profile, isLoading, isError } = useUserProfile(entityId);
  const lvl = riskMeta(profile?.risk_level);
  const score = profile?.risk_score ?? 0;
  const scoreTone = score > 70 ? 'text-blocked' : score > 40 ? 'text-flagged' : 'text-approved';
  const scoreBar = score > 70 ? 'bg-blocked' : score > 40 ? 'bg-flagged' : 'bg-approved';
  const flagRate = profile && profile.total_transactions > 0 ? profile.flagged_transactions / profile.total_transactions : 0;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-hidden border-border-strong bg-card sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-3 text-lg text-foreground">
            {isLoading ? (
              <Skeleton className="h-6 w-48" />
            ) : isError ? (
              <span className="text-blocked">Profil gagal dimuat</span>
            ) : profile ? (
              <>
                <span className="flex items-center gap-2">
                  <Shield className={cn('size-5', lvl.text)} aria-hidden />
                  Profil Risiko — {profile.name}
                </span>
                <span className={cn('inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium', lvl.pill)}>Risiko {lvl.label}</span>
              </>
            ) : null}
          </DialogTitle>
          {profile && (
            <DialogDescription className="text-muted-foreground">
              Ringkasan profil untuk entitas <span className="num">{profile.entity_id}</span>
            </DialogDescription>
          )}
        </DialogHeader>

        <ScrollArea className="max-h-[calc(90vh-96px)]">
          {isLoading && (
            <div className="space-y-4 pr-3">
              <Skeleton className="h-32 w-full" />
              <Skeleton className="h-32 w-full" />
            </div>
          )}

          {isError && (
            <div className="p-8 text-center text-blocked">
              <AlertTriangle className="mx-auto mb-2 size-8" aria-hidden />
              <p>Gagal memuat profil pengguna. Silakan coba lagi.</p>
            </div>
          )}

          {profile && (
            <div className="space-y-4 pr-3">
              <div className="grid gap-4 md:grid-cols-2">
                <section className={PANEL} aria-label="Informasi profil">
                  <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                    <UserIcon className="size-4 text-link" aria-hidden /> Informasi Profil
                  </h3>
                  <dl className="grid grid-cols-2 gap-3 text-sm">
                    <div><dt className="text-xs text-muted-foreground">ID entitas</dt><dd className="num text-foreground">{profile.entity_id}</dd></div>
                    <div><dt className="text-xs text-muted-foreground">Nama (tersamar)</dt><dd className="font-medium text-foreground">{profile.name}</dd></div>
                    <div>
                      <dt className="text-xs text-muted-foreground">Provinsi</dt>
                      <dd className="flex items-center gap-1.5 text-foreground"><MapPin className="size-3.5 text-muted-foreground" aria-hidden />{profile.province ?? '—'}</dd>
                    </div>
                    <div><dt className="text-xs text-muted-foreground">Total nilai transaksi</dt><dd className="num text-foreground">{formatIDR(profile.total_amount)}</dd></div>
                  </dl>
                </section>

                <section className={PANEL} aria-label="Penilaian risiko">
                  <h3 className="mb-3 text-sm font-semibold text-foreground">Penilaian Risiko</h3>
                  <div className="mb-4 flex items-center gap-3">
                    <span className={cn('num text-3xl font-semibold', scoreTone)}>{Math.round(score)}</span>
                    <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-inset" aria-hidden>
                      <div className={cn('h-2.5 rounded-full', scoreBar)} style={{ width: `${Math.min(score, 100)}%` }} />
                    </div>
                    <span className="text-xs text-muted-foreground">/ 100</span>
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    <Stat label="Total transaksi" value={formatInt(profile.total_transactions)} />
                    <Stat label="Ditandai" value={formatInt(profile.flagged_transactions)} className={profile.flagged_transactions > 0 ? 'text-flagged' : undefined} />
                    <Stat label="Rasio ditandai" value={formatPct(flagRate, 1)} />
                  </div>
                </section>
              </div>

              <section className={PANEL} aria-label="Rekomendasi tindakan">
                <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
                  <Flag className="size-4" aria-hidden /> Rekomendasi Tindakan
                </h3>
                <p className={cn('border-l-4 pl-3 text-sm leading-relaxed text-text-secondary', profile.risk_level === 'High' ? 'border-blocked' : profile.risk_level === 'Medium' ? 'border-flagged' : 'border-approved')}>
                  {RECOMMENDATION[profile.risk_level ?? ''] ?? RECOMMENDATION.Low}
                </p>
                <p className="mt-3 text-xs text-muted-foreground">
                  Riwayat aktivitas bulanan belum tersedia dari API; analisis naratif per transaksi tersedia di detail transaksi.
                </p>
              </section>

              <div className="flex justify-end border-t border-border pt-4">
                <button
                  type="button"
                  onClick={onClose}
                  className="inline-flex min-h-11 items-center rounded-lg border border-border-strong px-4 text-sm text-foreground transition-colors hover:bg-accent"
                >
                  Tutup
                </button>
              </div>
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
