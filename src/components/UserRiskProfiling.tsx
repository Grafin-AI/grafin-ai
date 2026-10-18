import { useState, useMemo } from 'react';
import { Input } from './ui/input';
import { Skeleton } from './ui/skeleton';
import { cn } from './ui/utils';
import { Search, Eye, AlertTriangle } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { UserProfileDetailsModal } from './UserProfileDetailsModal';
import { useUserRisk } from '../api/queries';
import { formatInt } from '../lib/format';
import { CHART, RISK_META, riskMeta } from '../lib/status';
import type { RiskProfile } from '../api/types';

/** Score is 0–100; color by band, independent of the stored level. */
function scoreMeta(score: number) {
  return score > 70 ? RISK_META.High : score > 40 ? RISK_META.Medium : RISK_META.Low;
}

const CARD = 'rounded-xl border border-border bg-card';

export function UserRiskProfiling() {
  const [searchTerm, setSearchTerm] = useState('');
  const [filterRisk, setFilterRisk] = useState('all');
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // API supports ?risk=High/Medium/Low
  const { data, isLoading, isError } = useUserRisk(filterRisk === 'all' ? undefined : filterRisk);
  const profiles: RiskProfile[] = useMemo(() => data?.profiles ?? [], [data]);

  const filteredProfiles = useMemo(() => {
    const q = searchTerm.toLowerCase();
    return profiles.filter((p) => !q || p.entity_id.toLowerCase().includes(q) || p.name.toLowerCase().includes(q));
  }, [profiles, searchTerm]);

  const riskDistributionData = useMemo(() => {
    const counts = { High: 0, Medium: 0, Low: 0 };
    profiles.forEach((p) => {
      const level = p.risk_level as keyof typeof counts;
      if (level in counts) counts[level]++;
    });
    return (Object.keys(counts) as (keyof typeof counts)[])
      .map((k) => ({ key: k, name: RISK_META[k].label, value: counts[k], color: RISK_META[k].hex }))
      .filter((d) => d.value > 0);
  }, [profiles]);

  const handleViewProfile = (entityId: string) => {
    setSelectedEntityId(entityId);
    setIsModalOpen(true);
  };
  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedEntityId(null);
  };

  return (
    <>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <section data-animate aria-label="Distribusi tingkat risiko" className={cn(CARD, 'p-4')}>
          <h2 className="mb-1 text-base font-semibold text-foreground">Distribusi Tingkat Risiko</h2>
          {isLoading ? (
            <Skeleton className="mt-2 h-40 w-full" />
          ) : riskDistributionData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie data={riskDistributionData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={4} dataKey="value" stroke="#0E1424">
                    {riskDistributionData.map((entry) => <Cell key={entry.key} fill={entry.color} />)}
                  </Pie>
                  <Tooltip contentStyle={CHART.tooltip} itemStyle={CHART.tooltipItem} formatter={(v, n) => [formatInt(Number(v)), n]} />
                </PieChart>
              </ResponsiveContainer>
              <ul className="mt-1 space-y-2">
                {riskDistributionData.map((item) => (
                  <li key={item.key} className="flex items-center gap-2 text-sm">
                    <span aria-hidden className="size-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                    <span className="flex-1 text-text-secondary">{item.name}</span>
                    <span className="num text-foreground">{formatInt(item.value)}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="mt-4 text-center text-sm text-muted-foreground">Belum ada data</p>
          )}
        </section>

        <section data-animate aria-label="Rincian tingkat risiko" className={cn(CARD, 'p-4 lg:col-span-2')}>
          <h2 className="mb-3 text-base font-semibold text-foreground">Rincian Tingkat Risiko (filter aktif)</h2>
          {isLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : riskDistributionData.length > 0 ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={riskDistributionData}>
                  <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" stroke={CHART.grid} tick={{ fontSize: 12, fill: CHART.axis }} />
                  <YAxis stroke={CHART.grid} tick={{ fontSize: 12, fill: CHART.axis }} tickFormatter={(v) => formatInt(v)} />
                  <Tooltip contentStyle={CHART.tooltip} labelStyle={CHART.tooltipLabel} itemStyle={CHART.tooltipItem} cursor={CHART.cursor} formatter={(v) => [formatInt(Number(v)), 'Profil']} />
                  <Bar dataKey="value" name="Profil" radius={[4, 4, 0, 0]}>
                    {riskDistributionData.map((entry) => <Cell key={entry.key} fill={entry.color} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="grid h-64 place-items-center text-sm text-muted-foreground">Belum ada data untuk filter ini</div>
          )}
        </section>
      </div>

      <section data-animate aria-label="Daftar profil risiko" className={cn(CARD, 'overflow-hidden')}>
        <div className="flex flex-col gap-3 border-b border-border px-[18px] py-3.5 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">Daftar Profil Risiko</h2>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {isLoading ? 'Memuat profil…' : `Menampilkan ${formatInt(filteredProfiles.length)} dari ${formatInt(profiles.length)} profil`}
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <label className="relative block">
              <span className="sr-only">Cari nama atau ID entitas</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                placeholder="Cari nama / ID entitas"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="h-11 pl-9 sm:w-64"
              />
            </label>
            <Select value={filterRisk} onValueChange={setFilterRisk}>
              <SelectTrigger className="h-11 w-full sm:w-44" aria-label="Filter tingkat risiko">
                <SelectValue placeholder="Tingkat risiko" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua tingkat</SelectItem>
                <SelectItem value="High">Tinggi</SelectItem>
                <SelectItem value="Medium">Sedang</SelectItem>
                <SelectItem value="Low">Rendah</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="max-h-[520px] overflow-auto">
          <table className="w-full min-w-[820px] border-collapse text-[13px]">
            <thead>
              <tr className="text-left text-muted-foreground">
                {['Entitas', 'Provinsi', 'Skor risiko', 'Tingkat', 'Total transaksi', 'Ditandai', ''].map((h, i) => (
                  <th key={i} scope="col" className={cn('sticky top-0 z-10 bg-card px-2 py-2.5 font-medium', i === 0 && 'pl-[18px]', i === 6 && 'pr-[18px]', (i === 4 || i === 5) && 'text-right')}>
                    {h || <span className="sr-only">Aksi</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading && Array.from({ length: 6 }).map((_, i) => (
                <tr key={i} className="border-t border-[#172138]">
                  {Array.from({ length: 7 }).map((__, j) => (
                    <td key={j} className={cn('px-2 py-3', j === 0 && 'pl-[18px]')}><Skeleton className="h-4 w-full max-w-28" /></td>
                  ))}
                </tr>
              ))}

              {isError && (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-blocked">
                    <AlertTriangle className="mx-auto mb-2 size-6" aria-hidden />
                    Gagal memuat data profil. Silakan muat ulang halaman.
                  </td>
                </tr>
              )}

              {!isLoading && !isError && filteredProfiles.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-muted-foreground">Tidak ada profil yang sesuai dengan filter.</td>
                </tr>
              )}

              {filteredProfiles.map((profile) => {
                const lvl = riskMeta(profile.risk_level);
                const sc = scoreMeta(profile.risk_score);
                return (
                  <tr key={profile.entity_id} className="border-t border-[#172138] transition-colors hover:bg-card-2">
                    <td className="py-2 pl-[18px] pr-2">
                      <div className="flex flex-col gap-0.5">
                        <span className="text-sm font-medium text-foreground">{profile.name}</span>
                        <span className="num text-xs text-muted-foreground">{profile.entity_id}</span>
                      </div>
                    </td>
                    <td className="px-2 py-2 text-text-secondary">{profile.province ?? '—'}</td>
                    <td className="px-2 py-2">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-border" aria-hidden>
                          <div className={cn('h-1.5', sc.bar)} style={{ width: `${Math.max(Math.min(profile.risk_score, 100), 2)}%` }} />
                        </div>
                        <span className={cn('num', sc.text)}>{Math.round(profile.risk_score)}</span>
                      </div>
                    </td>
                    <td className="px-2 py-2">
                      <span className={cn('inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium', lvl.pill)}>{lvl.label}</span>
                    </td>
                    <td className="num px-2 py-2 text-right text-foreground">{formatInt(profile.total_transactions)}</td>
                    <td className={cn('num px-2 py-2 text-right', profile.flagged_transactions > 0 ? 'font-medium text-flagged' : 'text-muted-foreground')}>
                      {formatInt(profile.flagged_transactions)}
                    </td>
                    <td className="py-1 pl-2 pr-[18px]">
                      <button
                        type="button"
                        onClick={() => handleViewProfile(profile.entity_id)}
                        aria-label={`Lihat profil ${profile.name}`}
                        className="inline-flex min-h-11 items-center gap-1.5 rounded-md px-2.5 text-xs text-link transition-colors hover:bg-accent hover:text-[#B5DDFC]"
                      >
                        <Eye className="size-3.5" aria-hidden />
                        Detail
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <UserProfileDetailsModal entityId={selectedEntityId} isOpen={isModalOpen} onClose={handleCloseModal} />
    </>
  );
}
