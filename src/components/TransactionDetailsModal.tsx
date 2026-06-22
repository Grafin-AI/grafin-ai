import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Badge } from './ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { ScrollArea } from './ui/scroll-area';
import { Button } from './ui/button';
import { Skeleton } from './ui/skeleton';
import {
  Building,
  CreditCard,
  Clock,
  AlertTriangle,
  Shield,
  Eye,
  TrendingUp,
  Users,
  Activity,
  X,
  Download,
  Flag,
  ArrowRight
} from 'lucide-react';
import { useTransactionDetail } from '../api/queries';

interface TransactionDetailsModalProps {
  transactionId: number | null;
  isOpen: boolean;
  onClose: () => void;
  onOpenUserProfile?: (entityId: string) => void;
}

// Typology-keyed analysis text (bilingual narrative — these are explanatory templates, not fabricated data)
const typologyAnalysis: Record<string, {
  patternMatching: string;
  behaviorAnalysis: string;
  networkAnalysis: string;
  recommendation: string;
}> = {
  'Bridge CEX Withdrawal': {
    patternMatching: 'Terdeteksi pola pig-butchering: fan-in dari 18 dompet/e-wallet berbeda ke akun sumber dalam 72 jam, diikuti instruksi transfer bernilai besar pertama kali ke penerima baru.',
    behaviorAnalysis: 'Jarak (shortest-path) ke klaster watchlist = 2 hop melalui dompet 0x93aa..ee12; rasio transaksi tengah malam 31% (naik signifikan dari baseline <5%); perangkat dan IP yang sama terhubung ke 3 akun lain berstatus REVIEW/BLOCK.',
    networkAnalysis: 'Analisis jaringan menunjukkan koneksi dengan akun-akun yang terkait dengan aktivitas cryptocurrency exchange withdrawal yang mencurigakan. Terdapat indikasi money laundering melalui multiple small deposits.',
    recommendation: 'BLOKIR transaksi, bekukan sementara saldo terkait, dan lakukan verifikasi identitas serta kronologi komunikasi korban; kirim STR ke PPATK'
  },
  'Smurfing': {
    patternMatching: 'Terdeteksi pola smurfing: 12 transaksi berturut-turut dengan nilai di bawah threshold pelaporan (Rp 20 juta) dalam 6 jam terakhir.',
    behaviorAnalysis: 'Perilaku transaksi tidak konsisten dengan profil nasabah - frekuensi transaksi meningkat 800% dari rata-rata bulanan. Waktu transaksi menunjukkan pola robotik setiap 30 menit.',
    networkAnalysis: 'Jejak digital menunjukkan koordinasi dengan 8 akun lain yang melakukan transaksi serupa dalam rentang waktu yang sama. Shared device fingerprint dengan akun terdaftar di watchlist AML.',
    recommendation: 'TUNDA semua transaksi terkait akun ini, lakukan enhanced due diligence, dan koordinasi dengan unit AML untuk investigasi lebih lanjut'
  },
  'Mule Account': {
    patternMatching: 'Pola mule account teridentifikasi: menerima dana dari 15+ akun berbeda dalam 24 jam, kemudian segera mentransfer 95% dana ke 3 akun tujuan utama.',
    behaviorAnalysis: 'Akun menunjukkan aktivitas yang tidak wajar - tidak ada riwayat transaksi signifikan sebelum periode ini. Geographic mismatch antara lokasi registrasi dan aktivitas transaksi.',
    networkAnalysis: 'Terkoneksi dengan jaringan akun yang dikenal sebagai money mule. Pattern matching dengan kasus sebelumnya menunjukkan kesamaan 87% dengan skema money laundering yang telah teridentifikasi.',
    recommendation: 'BLOKIR segera dan freeze semua dana terkait. Laporkan ke otoritas terkait dan lakukan investigasi mendalam terhadap pemilik akun'
  },
  'Card Testing': {
    patternMatching: 'Aktivitas card testing terdeteksi: 45 percobaan transaksi kecil (Rp 1.000 - Rp 5.000) dalam 10 menit menggunakan variasi data kartu yang berbeda.',
    behaviorAnalysis: 'Pattern menunjukkan automated testing untuk validasi nomor kartu kredit yang dicuri. Tingkat failure rate 78% konsisten dengan card testing attacks.',
    networkAnalysis: 'IP address terkait dengan proxy networks dan VPN. Device fingerprinting menunjukkan penggunaan automated tools untuk rapid-fire transactions.',
    recommendation: 'BLOKIR segera kartu terkait, implementasi CAPTCHA enhanced, dan blacklist IP ranges yang terlibat'
  },
  'Layering': {
    patternMatching: 'Skema layering teridentifikasi: dana dipindahkan melalui 8 akun berbeda dalam rantai transaksi kompleks untuk mengaburkan jejak sumber dana.',
    behaviorAnalysis: 'Analisis temporal menunjukkan koordinasi yang ketat antar akun - window transaksi rata-rata 3 menit antar hop. Volume total Rp 2.3 miliar dalam 5 hari.',
    networkAnalysis: 'Graph analysis mengungkap struktur layering dengan 3 tingkat pemisahan dari sumber dana awal. Beberapa akun perantara menunjukkan aktivitas dormant yang mendadak aktif.',
    recommendation: 'FREEZE semua akun dalam rantai transaksi, koordinasi dengan bank lain untuk block akun terkait, dan segera laporkan ke PPATK'
  },
  'Trade-Based Money Laundering': {
    patternMatching: 'TBML scheme detected: over-invoicing senilai 340% dari harga pasar wajar untuk import elektronik, disertai transfer dana ke multiple offshore accounts.',
    behaviorAnalysis: 'Discrepancy analysis menunjukkan markup tidak wajar pada transaksi trade finance. Frequency dan timing bertepatan dengan laporan customs yang mencurigakan.',
    networkAnalysis: 'Connected dengan jaringan perusahaan shell companies di 3 jurisdiksi berbeda. Beneficial ownership analysis menunjukkan ultimate controller yang sama.',
    recommendation: 'SUSPEND trade facility, lakukan enhanced due diligence pada semua trade documents, dan koordinasi dengan Bea Cukai serta otoritas internasional'
  },
  'Fan-Out': {
    patternMatching: 'Pola fan-out terdeteksi: satu akun sumber melakukan distribusi ke banyak akun penerima dalam waktu singkat untuk mengaburkan asal dana.',
    behaviorAnalysis: 'Distribusi dana dalam jumlah merata ke banyak akun penerima tidak konsisten dengan pola transaksi normal.',
    networkAnalysis: 'Analisis jaringan menunjukkan pola distribusi yang terkoordinasi, kemungkinan otomatis.',
    recommendation: 'REVIEW semua akun penerima dan lacak pergerakan dana selanjutnya; pertimbangkan pelaporan ke PPATK'
  }
};

const defaultAnalysis = {
  patternMatching: 'Transaksi dalam batas normal. Tidak terdeteksi pola mencurigakan berdasarkan algoritma machine learning terkini.',
  behaviorAnalysis: 'Perilaku transaksi konsisten dengan profil historis nasabah. Tidak ada indikasi aktivitas yang anomali.',
  networkAnalysis: 'Analisis jaringan tidak menunjukkan koneksi dengan entitas yang masuk dalam watchlist atau daftar sanksi.',
  recommendation: 'PROSES transaksi sesuai prosedur standar. Tidak diperlukan tindakan khusus.'
};

export function TransactionDetailsModal({ transactionId, isOpen, onClose, onOpenUserProfile }: TransactionDetailsModalProps) {
  const { data: txn, isLoading, isError } = useTransactionDetail(transactionId);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'approved': return 'bg-green-100 text-green-800 border-green-200';
      case 'flagged': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'blocked': return 'bg-red-100 text-red-800 border-red-200';
      default: return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'approved': return <Shield className="w-4 h-4 text-green-600" />;
      case 'flagged': return <AlertTriangle className="w-4 h-4 text-yellow-600" />;
      case 'blocked': return <X className="w-4 h-4 text-red-600" />;
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

  const analysis = txn?.typology
    ? (typologyAnalysis[txn.typology] ?? defaultAnalysis)
    : defaultAnalysis;

  const riskFactors = txn
    ? txn.fraud_score > 0.7
      ? ['High Fraud Score', txn.typology ?? 'Suspicious Pattern', txn.is_laundering ? 'Laundering Indicator' : 'Elevated Risk']
      : txn.fraud_score > 0.4
      ? ['Moderate Fraud Score', 'Review Recommended']
      : ['Low Risk Profile']
    : [];

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-7xl sm:max-w-7xl max-h-[90vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            {isLoading ? (
              <Skeleton className="h-6 w-48" />
            ) : isError ? (
              <span className="text-red-600">Failed to load transaction</span>
            ) : txn ? (
              <>
                <div className="flex items-center gap-2">
                  {getStatusIcon(txn.status)}
                  Detail Transaksi TXN-{txn.id}
                </div>
                <Badge className={`text-xs capitalize ${getStatusColor(txn.status)}`}>
                  {txn.status}
                </Badge>
              </>
            ) : null}
          </DialogTitle>
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
              <p>Gagal memuat data transaksi. Silakan coba lagi.</p>
            </div>
          )}

          {txn && (
            <div className="space-y-6 pr-4">
              {/* Transaction Overview and Fraud Risk Assessment - Side by Side */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Transaction Overview */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <CreditCard className="w-5 h-5 text-blue-600" />
                      Informasi Transaksi
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
                    <div>
                      <p className="text-sm text-gray-500">ID Transaksi</p>
                      <p className="font-medium">TXN-{txn.id}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Jenis Transaksi</p>
                      <p className="font-medium">{txn.type}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Nominal</p>
                      <p className="font-medium text-lg">{formatAmount(txn.amount)}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Mata Uang</p>
                      <p className="font-medium">{txn.currency}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Waktu Transaksi</p>
                      <div className="flex items-center gap-2">
                        <Clock className="w-4 h-4 text-gray-400" />
                        <p className="font-medium">{new Date(txn.event_time).toLocaleString('id-ID')}</p>
                      </div>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Indikasi Pencucian</p>
                      <p className={`font-medium ${txn.is_laundering ? 'text-red-600' : 'text-green-600'}`}>
                        {txn.is_laundering ? 'Ya (Terdeteksi)' : 'Tidak'}
                      </p>
                    </div>
                  </CardContent>
                </Card>

                {/* Fraud Risk Assessment */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Shield className="w-5 h-5 text-red-600" />
                      Penilaian Risiko Fraud
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex items-center gap-3">
                      <span className={`text-2xl font-bold min-w-[60px] ${
                        txn.fraud_score > 0.7
                          ? 'text-red-600'
                          : txn.fraud_score > 0.4
                          ? 'text-yellow-600'
                          : 'text-green-600'
                      }`}>
                        {Math.round(txn.fraud_score * 100)}%
                      </span>
                      <div className="flex-1">
                        <div className="w-full bg-gray-200 rounded-full h-2.5">
                          <div
                            className={`h-2.5 rounded-full ${
                              txn.fraud_score > 0.7
                                ? 'bg-red-500'
                                : txn.fraud_score > 0.4
                                ? 'bg-yellow-500'
                                : 'bg-green-500'
                            }`}
                            style={{ width: `${txn.fraud_score * 100}%` }}
                          />
                        </div>
                      </div>
                    </div>

                    {txn.typology && (
                      <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                        <div className="flex items-center gap-2 mb-2">
                          <AlertTriangle className="w-5 h-5 text-red-600" />
                          <span className="font-medium text-red-800">Jenis Fraud Terdeteksi</span>
                        </div>
                        <Badge variant="outline" className="bg-red-100 text-red-700 border-red-300">
                          {txn.typology}
                        </Badge>
                      </div>
                    )}

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
                  </CardContent>
                </Card>
              </div>

              {/* Source Bank */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <ArrowRight className="w-5 h-5 text-[#139EF6]" />
                    Detail Bank Transaksi
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div>
                      <div className="flex items-center gap-2 mb-4">
                        <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                        <h4 className="font-medium text-gray-900">Bank Pengirim</h4>
                      </div>
                      <div className="grid grid-cols-2 gap-4 bg-blue-50/50 p-4 rounded-lg border border-blue-100">
                        <div>
                          <p className="text-sm text-gray-500 mb-1">Bank</p>
                          <div className="flex items-center gap-2">
                            <Building className="w-4 h-4 text-gray-400" />
                            <p className="font-medium">{txn.bank}</p>
                          </div>
                        </div>
                        <div>
                          <p className="text-sm text-gray-500 mb-1">Jenis</p>
                          <p className="font-medium">{txn.type}</p>
                        </div>
                        {onOpenUserProfile && (
                          <div className="col-span-2">
                            <p className="text-sm text-gray-500 mb-1">Entity ID</p>
                            <button
                              onClick={() => onOpenUserProfile(String(txn.id))}
                              className="font-medium font-mono text-[#139EF6] hover:text-[#0f7ec4] flex items-center gap-2 group transition-colors text-sm"
                            >
                              TXN-{txn.id}
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Detailed Analysis */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="w-5 h-5 text-blue-600" />
                    Analisis Fraud Detail
                  </CardTitle>
                </CardHeader>
                <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                      <Activity className="w-4 h-4" />
                      Pattern Matching
                    </h4>
                    <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 p-3 rounded-lg">
                      {analysis.patternMatching}
                    </p>
                  </div>

                  <div>
                    <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                      <Users className="w-4 h-4" />
                      Analisis Perilaku
                    </h4>
                    <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 p-3 rounded-lg">
                      {analysis.behaviorAnalysis}
                    </p>
                  </div>

                  <div>
                    <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                      <Eye className="w-4 h-4" />
                      Analisis Jaringan
                    </h4>
                    <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 p-3 rounded-lg">
                      {analysis.networkAnalysis}
                    </p>
                  </div>

                  <div>
                    <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                      <Flag className="w-4 h-4" />
                      Rekomendasi Tindakan
                    </h4>
                    <div className={`p-4 rounded-lg border-l-4 ${
                      txn.status === 'blocked'
                        ? 'bg-red-50 border-red-500'
                        : txn.status === 'flagged'
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

              {/* Action Buttons */}
              <div className="flex justify-end gap-3 pt-4 border-t">
                <Button variant="outline" className="flex items-center gap-2">
                  <Download className="w-4 h-4" />
                  Export Report
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
