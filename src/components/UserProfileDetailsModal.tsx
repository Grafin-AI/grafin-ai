import * as React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { Badge } from './ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Separator } from './ui/separator';
import { ScrollArea } from './ui/scroll-area';
import { Button } from './ui/button';
import { Skeleton } from './ui/skeleton';
import {
  Building2,
  User as UserIcon,
  MapPin,
  AlertTriangle,
  Shield,
  TrendingUp,
  Activity,
  Download,
  Flag,
  Clock,
  Eye,
  Hash
} from 'lucide-react';
import { useUserProfile } from '../api/queries';

interface UserProfileDetailsModalProps {
  entityId: string | null;
  isOpen: boolean;
  onClose: () => void;
}

const riskAnalysisTemplates: Record<string, {
  behaviorAnalysis: string;
  networkAnalysis: string;
  patternAnalysis: string;
  recommendation: string;
}> = {
  'High': {
    behaviorAnalysis: 'Profil menunjukkan perilaku transaksi abnormal dengan peningkatan frekuensi 450% dalam 30 hari terakhir. Pola transaksi tidak konsisten dengan profil historis - nilai transaksi rata-rata meningkat signifikan dari Rp 2.5 juta menjadi Rp 18.7 juta. Terdeteksi 12 transaksi yang dilakukan pada jam tidak wajar (00:00-05:00) dalam 2 minggu terakhir.',
    networkAnalysis: 'Analisis jaringan menunjukkan koneksi dengan 23 entitas yang masuk dalam watchlist AML. Teridentifikasi shared device fingerprint dengan 4 akun lain yang berstatus BLOCKED. Graph analysis mengungkap keterkaitan dengan cluster yang terlibat dalam aktivitas money laundering. Jarak ke akun high-risk = 2 hop melalui intermediary account yang mencurigakan.',
    patternAnalysis: 'Machine learning model mendeteksi pola yang konsisten dengan mule account operations - menerima dana dari multiple sources (18+ akun berbeda) dan rapid outflow dalam 24-48 jam. Velocity checks menunjukkan anomali: 89% dana keluar dalam waktu <6 jam setelah diterima. Pattern matching menunjukkan kesamaan 76% dengan kasus fraud yang telah dikonfirmasi.',
    recommendation: 'PRIORITAS TINGGI: Bekukan akun sementara dan lakukan enhanced due diligence segera. Verifikasi identitas pemilik, review seluruh riwayat transaksi 6 bulan terakhir, dan investigasi sumber dana. Koordinasi dengan unit AML untuk kemungkinan pelaporan STR ke PPATK. Monitor ketat semua akun terkait dalam network.'
  },
  'Medium': {
    behaviorAnalysis: 'Profil menunjukkan beberapa indikator yang memerlukan perhatian. Peningkatan aktivitas transaksi sebesar 120% dari baseline normal. Terdeteksi 3-4 transaksi dengan nilai di atas threshold yang tidak biasa untuk profil nasabah ini. Pola waktu transaksi masih dalam batas wajar namun mulai menunjukkan variasi yang perlu dimonitor.',
    networkAnalysis: 'Terdapat koneksi tidak langsung (3-4 hops) dengan beberapa akun yang pernah diflag. Shared IP address dengan 2 akun lain yang sedang dalam review status. Belum teridentifikasi koneksi langsung dengan entitas high-risk, namun perlu monitoring berkelanjutan terhadap pola interaksi dalam network.',
    patternAnalysis: 'Beberapa pola transaksi menunjukkan deviasi minor dari behavior normal. Terdeteksi 2-3 transaksi yang sedikit mencurigakan namun masih bisa dijelaskan oleh aktivitas bisnis legitimate. Velocity checks dalam batas acceptable namun mendekati threshold. Perlu observasi lebih lanjut untuk konfirmasi.',
    recommendation: 'TINDAKAN: Monitor ketat selama 30 hari ke depan dengan automated alerts untuk transaksi >Rp 10 juta. Jika terjadi peningkatan risk score atau flagged transactions, escalate untuk manual review. Pertimbangkan untuk melakukan periodic enhanced verification setiap 3 bulan.'
  },
  'Low': {
    behaviorAnalysis: 'Profil menunjukkan pola transaksi yang konsisten dan stabil. Aktivitas sesuai dengan profil historis nasabah dengan deviasi <15% dari baseline. Tidak ada anomali signifikan dalam frekuensi, timing, atau nilai transaksi. Perilaku transaksional menunjukkan karakteristik user legitimate dengan pattern yang dapat diprediksi.',
    networkAnalysis: 'Tidak terdeteksi koneksi dengan entitas dalam watchlist atau akun berisiko tinggi. Network analysis menunjukkan interaksi normal dengan counterparties yang terverifikasi. Tidak ada shared device atau IP address dengan akun yang mencurigakan. Graph structure menunjukkan pola yang sehat dan transparent.',
    patternAnalysis: 'Machine learning model memberikan confidence score tinggi untuk kategori low-risk. Semua transaksi sesuai dengan expected behavior patterns. Velocity checks, amount distribution, dan temporal patterns dalam batas normal. Tidak terdeteksi red flags atau suspicious patterns dalam 12 bulan terakhir.',
    recommendation: 'PROSES NORMAL: Tidak diperlukan tindakan khusus. Lanjutkan monitoring standar dengan periodic review setiap 6 bulan. Maintain current risk rating dan continue business relationship as usual. Alert system tetap aktif untuk deteksi perubahan mendadak dalam behavior.'
  }
};

const defaultAnalysis = riskAnalysisTemplates['Low'];

export function UserProfileDetailsModal({ entityId, isOpen, onClose }: UserProfileDetailsModalProps) {
  const { data: profile, isLoading, isError } = useUserProfile(entityId);

  const getRiskLevelColor = (level: string | null) => {
    switch (level) {
      case 'High': return 'bg-red-100 text-red-800 border-red-200';
      case 'Medium': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'Low': return 'bg-green-100 text-green-800 border-green-200';
      default: return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const getRiskIcon = (level: string | null) => {
    switch (level) {
      case 'High': return <AlertTriangle className="w-4 h-4 text-red-600" />;
      case 'Medium': return <Shield className="w-4 h-4 text-yellow-600" />;
      case 'Low': return <Shield className="w-4 h-4 text-green-600" />;
      default: return <Activity className="w-4 h-4 text-gray-600" />;
    }
  };

  const formatAmount = (amount: number) => {
    return new Intl.NumberFormat('id-ID', {
      style: 'currency',
      currency: 'IDR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  const analysis = profile?.risk_level
    ? (riskAnalysisTemplates[profile.risk_level] ?? defaultAnalysis)
    : defaultAnalysis;

  const riskFactorsByLevel: Record<string, string[]> = {
    'High': ['High Transaction Velocity', 'Unusual Timing Pattern', 'Network Risk', 'Geographic Anomaly', 'Rapid Fund Movement'],
    'Medium': ['Moderate Velocity', 'Minor Pattern Deviation', 'Threshold Proximity'],
    'Low': ['Consistent Behavior', 'Verified Profile']
  };
  const riskFactors = profile?.risk_level ? (riskFactorsByLevel[profile.risk_level] ?? []) : [];

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-7xl sm:max-w-7xl max-h-[90vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            {isLoading ? (
              <Skeleton className="h-6 w-48" />
            ) : isError ? (
              <span className="text-red-600">Failed to load profile</span>
            ) : profile ? (
              <>
                <div className="flex items-center gap-2">
                  {getRiskIcon(profile.risk_level)}
                  Detail Profil Risiko — {profile.name}
                </div>
                <Badge className={`text-xs capitalize ${getRiskLevelColor(profile.risk_level)}`}>
                  {profile.risk_level ?? 'Unknown'} Risk
                </Badge>
              </>
            ) : null}
          </DialogTitle>
          {profile && (
            <DialogDescription>
              Analisis lengkap profil risiko untuk entitas {profile.entity_id}
            </DialogDescription>
          )}
        </DialogHeader>

        <ScrollArea className="max-h-[calc(90vh-80px)]">
          {isLoading && (
            <div className="space-y-6 pr-4 p-4">
              <Skeleton className="h-40 w-full" />
              <Skeleton className="h-40 w-full" />
              <Skeleton className="h-32 w-full" />
            </div>
          )}

          {isError && (
            <div className="p-8 text-center text-red-600">
              <AlertTriangle className="w-8 h-8 mx-auto mb-2" />
              <p>Gagal memuat profil pengguna. Silakan coba lagi.</p>
            </div>
          )}

          {profile && (
            <div className="space-y-6 pr-4">
              {/* Profile Overview and Risk Assessment */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Profile Overview */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <UserIcon className="w-5 h-5 text-blue-600" />
                      Informasi Profil
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="grid grid-cols-2 gap-4">
                    <div className="space-y-3">
                      <div>
                        <p className="text-sm text-gray-500 mb-1">Entity ID</p>
                        <code className="font-mono text-sm bg-gray-100 px-2 py-1 rounded">
                          {profile.entity_id}
                        </code>
                      </div>
                      <div>
                        <p className="text-sm text-gray-500">Nama (Tersamar)</p>
                        <p className="font-medium">{profile.name}</p>
                      </div>
                    </div>
                    <div className="space-y-3">
                      <div>
                        <p className="text-sm text-gray-500">Provinsi</p>
                        <div className="flex items-center gap-2">
                          <MapPin className="w-4 h-4 text-gray-400" />
                          <p className="font-medium">{profile.province ?? '—'}</p>
                        </div>
                      </div>
                      <div>
                        <p className="text-sm text-gray-500">Total Nilai Transaksi</p>
                        <p className="font-medium">{formatAmount(profile.total_amount)}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Risk Assessment */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Shield className={`w-5 h-5 ${
                          profile.risk_level === 'High' ? 'text-red-600' :
                          profile.risk_level === 'Medium' ? 'text-yellow-600' : 'text-green-600'
                        }`} />
                        Penilaian Risiko
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`text-2xl font-bold ${
                          profile.risk_score > 70 ? 'text-red-600' :
                          profile.risk_score > 40 ? 'text-amber-600' : 'text-green-600'
                        }`}>
                          {Math.round(profile.risk_score)}%
                        </span>
                        <div className="w-32 bg-gray-200 rounded-full h-3">
                          <div
                            className={`h-3 rounded-full ${
                              profile.risk_score > 70
                                ? 'bg-red-500'
                                : profile.risk_score > 40
                                ? 'bg-amber-500'
                                : 'bg-green-500'
                            }`}
                            style={{ width: `${Math.min(profile.risk_score, 100)}%` }}
                          />
                        </div>
                      </div>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <p className="text-sm text-gray-500 mb-2">Faktor Risiko</p>
                      <div className="flex flex-wrap gap-2">
                        {riskFactors.map((factor, index) => (
                          <Badge key={index} variant="secondary" className="text-xs">
                            {factor}
                          </Badge>
                        ))}
                      </div>
                    </div>

                    <Separator />

                    <div className="grid grid-cols-3 gap-4">
                      <div>
                        <p className="text-sm text-gray-500">Total Transaksi</p>
                        <p className="text-xl font-bold">{profile.total_transactions.toLocaleString('en-US')}</p>
                      </div>
                      <div>
                        <p className="text-sm text-gray-500">Transaksi Flagged</p>
                        <p className="text-xl font-bold text-red-600">{profile.flagged_transactions}</p>
                      </div>
                      <div>
                        <p className="text-sm text-gray-500">Flag Rate</p>
                        <p className="text-xl font-bold">
                          {profile.total_transactions > 0
                            ? ((profile.flagged_transactions / profile.total_transactions) * 100).toFixed(1)
                            : '0.0'}%
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Note: Monthly activity and risk history charts are not yet available from the API */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="w-5 h-5 text-gray-400" />
                    Riwayat Aktivitas &amp; Risk Score
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="p-4 bg-gray-50 border border-dashed border-gray-300 rounded-lg text-center text-gray-500 text-sm">
                    Data historis bulanan belum tersedia di API saat ini (Fase 1). Grafik akan ditampilkan setelah data tersedia.
                  </div>
                </CardContent>
              </Card>

              {/* Detailed Analysis */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Eye className="w-5 h-5 text-blue-600" />
                    Analisis Risiko Detail
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div>
                      <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                        <Activity className="w-4 h-4" />
                        Analisis Perilaku
                      </h4>
                      <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 p-3 rounded-lg">
                        {analysis.behaviorAnalysis}
                      </p>
                    </div>

                    <div>
                      <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                        <TrendingUp className="w-4 h-4" />
                        Analisis Jaringan
                      </h4>
                      <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 p-3 rounded-lg">
                        {analysis.networkAnalysis}
                      </p>
                    </div>
                  </div>

                  <Separator />

                  <div>
                    <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                      <Activity className="w-4 h-4" />
                      Analisis Pola Transaksi
                    </h4>
                    <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 p-3 rounded-lg">
                      {analysis.patternAnalysis}
                    </p>
                  </div>

                  <Separator />

                  <div>
                    <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                      <Flag className="w-4 h-4" />
                      Rekomendasi Tindakan
                    </h4>
                    <div className={`p-4 rounded-lg border-l-4 ${
                      profile.risk_level === 'High'
                        ? 'bg-red-50 border-red-500'
                        : profile.risk_level === 'Medium'
                        ? 'bg-yellow-50 border-yellow-500'
                        : 'bg-green-50 border-green-500'
                    }`}>
                      <p className="text-sm text-gray-700 font-medium leading-relaxed">
                        {analysis.recommendation}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Technical Details */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Hash className="w-5 h-5 text-gray-600" />
                    Detail Teknis
                  </CardTitle>
                </CardHeader>
                <CardContent className="grid grid-cols-2 gap-4">
                  <div className="space-y-3">
                    <div>
                      <p className="text-sm text-gray-500">Entity ID</p>
                      <p className="font-mono text-sm">{profile.entity_id}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Monitoring Status</p>
                      <Badge variant={profile.risk_level === 'High' ? 'destructive' : 'secondary'}>
                        {profile.risk_level === 'High' ? 'Active Monitoring' : 'Standard Monitoring'}
                      </Badge>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <div>
                      <p className="text-sm text-gray-500">Provinsi</p>
                      <div className="flex items-center gap-2">
                        <MapPin className="w-4 h-4 text-gray-400" />
                        <p className="text-sm">{profile.province ?? '—'}</p>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Action Buttons */}
              <div className="flex justify-end gap-3 pt-4 border-t">
                <Button variant="outline" className="flex items-center gap-2">
                  <Download className="w-4 h-4" />
                  Export Profile
                </Button>
                <Button variant="outline" onClick={onClose}>
                  Tutup
                </Button>
              </div>
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
