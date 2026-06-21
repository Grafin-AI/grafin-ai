import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Badge } from './ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Separator } from './ui/separator';
import { ScrollArea } from './ui/scroll-area';
import { Button } from './ui/button';
import { 
  Building, 
  CreditCard, 
  Clock, 
  MapPin, 
  AlertTriangle, 
  Shield, 
  Eye, 
  TrendingUp,
  Users,
  Activity,
  X,
  Download,
  Flag,
  ExternalLink,
  ArrowRight
} from 'lucide-react';

interface Transaction {
  id: string;
  bank: string;
  amount: number;
  fraudScore: number;
  timestamp: string;
  status: 'approved' | 'flagged' | 'blocked';
  type: string;
  suspectedFraudType: string | null;
}

interface ExtendedTransaction extends Transaction {
  // Additional metadata
  accountNumber: string;
  recipientBank: string;
  recipientAccount: string;
  sourcePaymentId: string;
  destinationPaymentId: string;
  ipAddress: string;
  location: string;
  deviceId: string;
  sessionId: string;
  referenceNumber: string;
  merchantId?: string;
  channelType: string;
  processingTime: string;
  riskFactors: string[];
  analysisDetails: {
    patternMatching: string;
    behaviorAnalysis: string;
    networkAnalysis: string;
    recommendation: string;
  };
}

interface TransactionDetailsModalProps {
  transaction: Transaction | null;
  isOpen: boolean;
  onClose: () => void;
  onOpenUserProfile?: (paymentId: string) => void;
}

// Generate extended transaction data based on base transaction
const generateExtendedData = (transaction: Transaction): ExtendedTransaction => {
  const analysisTemplates = {
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
    }
  };

  const analysis = analysisTemplates[transaction.suspectedFraudType as keyof typeof analysisTemplates] || {
    patternMatching: 'Transaksi dalam batas normal. Tidak terdeteksi pola mencurigakan berdasarkan algoritma machine learning terkini.',
    behaviorAnalysis: 'Perilaku transaksi konsisten dengan profil historis nasabah. Tidak ada indikasi aktivitas yang anomali.',
    networkAnalysis: 'Analisis jaringan tidak menunjukkan koneksi dengan entitas yang masuk dalam watchlist atau daftar sanksi.',
    recommendation: 'PROSES transaksi sesuai prosedur standar. Tidak diperlukan tindakan khusus.'
  };

  return {
    ...transaction,
    accountNumber: `${Math.floor(Math.random() * 9000000000) + 1000000000}`,
    recipientBank: ['Bank BCA', 'Bank Mandiri', 'Bank BRI', 'Bank BNI', 'Bank CIMB'][Math.floor(Math.random() * 5)],
    recipientAccount: `${Math.floor(Math.random() * 9000000000) + 1000000000}`,
    sourcePaymentId: `PAY-${Math.random().toString(36).substr(2, 10).toUpperCase()}`,
    destinationPaymentId: `PAY-${Math.random().toString(36).substr(2, 10).toUpperCase()}`,
    ipAddress: `${Math.floor(Math.random() * 255)}.${Math.floor(Math.random() * 255)}.${Math.floor(Math.random() * 255)}.${Math.floor(Math.random() * 255)}`,
    location: ['Jakarta', 'Surabaya', 'Bandung', 'Medan', 'Semarang', 'Makassar', 'Denpasar'][Math.floor(Math.random() * 7)],
    deviceId: `DVC-${Math.random().toString(36).substr(2, 12).toUpperCase()}`,
    sessionId: `SES-${Math.random().toString(36).substr(2, 16).toUpperCase()}`,
    referenceNumber: `REF${new Date().getFullYear()}${Math.floor(Math.random() * 1000000000)}`,
    merchantId: transaction.type === 'Purchase' ? `MRC-${Math.random().toString(36).substr(2, 8).toUpperCase()}` : undefined,
    channelType: ['Internet Banking', 'Mobile Banking', 'ATM', 'Phone Banking'][Math.floor(Math.random() * 4)],
    processingTime: `${Math.floor(Math.random() * 500) + 100}ms`,
    riskFactors: transaction.fraudScore > 0.7 
      ? ['High Velocity', 'Unusual Timing', 'Geographic Anomaly', 'Device Mismatch', 'Network Risk']
      : transaction.fraudScore > 0.4 
      ? ['Moderate Velocity', 'Time Pattern']
      : ['Low Risk Profile'],
    analysisDetails: analysis
  };
};

export function TransactionDetailsModal({ transaction, isOpen, onClose, onOpenUserProfile }: TransactionDetailsModalProps) {
  if (!transaction) return null;

  const extendedTransaction = generateExtendedData(transaction);

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

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-7xl sm:max-w-7xl max-h-[90vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              {getStatusIcon(extendedTransaction.status)}
              Detail Transaksi {extendedTransaction.id}
            </div>
            <Badge className={`text-xs capitalize ${getStatusColor(extendedTransaction.status)}`}>
              {extendedTransaction.status}
            </Badge>
          </DialogTitle>
        </DialogHeader>

        <ScrollArea className="max-h-[calc(90vh-80px)]">
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
                    <p className="font-medium">{extendedTransaction.id}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Jenis Transaksi</p>
                    <p className="font-medium">{extendedTransaction.type}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Nominal</p>
                    <p className="font-medium text-lg">{formatAmount(extendedTransaction.amount)}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Waktu Transaksi</p>
                    <div className="flex items-center gap-2">
                      <Clock className="w-4 h-4 text-gray-400" />
                      <p className="font-medium">{extendedTransaction.timestamp}</p>
                    </div>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Kanal Transaksi</p>
                    <p className="font-medium">{extendedTransaction.channelType}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Waktu Proses</p>
                    <p className="font-medium">{extendedTransaction.processingTime}</p>
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
                      extendedTransaction.fraudScore > 0.7 
                        ? 'text-red-600' 
                        : extendedTransaction.fraudScore > 0.4 
                        ? 'text-yellow-600' 
                        : 'text-green-600'
                    }`}>
                      {Math.round(extendedTransaction.fraudScore * 100)}%
                    </span>
                    <div className="flex-1">
                      <div className="w-full bg-gray-200 rounded-full h-2.5">
                        <div 
                          className={`h-2.5 rounded-full ${
                            extendedTransaction.fraudScore > 0.7 
                              ? 'bg-red-500' 
                              : extendedTransaction.fraudScore > 0.4 
                              ? 'bg-yellow-500' 
                              : 'bg-green-500'
                          }`}
                          style={{ width: `${extendedTransaction.fraudScore * 100}%` }}
                        />
                      </div>
                    </div>
                  </div>
                  
                  {extendedTransaction.suspectedFraudType && (
                    <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                      <div className="flex items-center gap-2 mb-2">
                        <AlertTriangle className="w-5 h-5 text-red-600" />
                        <span className="font-medium text-red-800">Jenis Fraud Terdeteksi</span>
                      </div>
                      <Badge variant="outline" className="bg-red-100 text-red-700 border-red-300">
                        {extendedTransaction.suspectedFraudType}
                      </Badge>
                    </div>
                  )}
                  
                  <div>
                    <p className="text-sm text-gray-500 mb-2">Faktor Risiko</p>
                    <div className="flex flex-wrap gap-2">
                      {extendedTransaction.riskFactors.map((factor, index) => (
                        <Badge key={index} variant="secondary" className="text-xs">
                          {factor}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Account Details Section - Source and Destination */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ArrowRight className="w-5 h-5 text-[#139EF6]" />
                  Detail Akun Transaksi
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Source Account Details */}
                  <div>
                    <div className="flex items-center gap-2 mb-4">
                      <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                      <h4 className="font-medium text-gray-900">Sumber Dana</h4>
                    </div>
                    <div className="grid grid-cols-2 gap-4 bg-blue-50/50 p-4 rounded-lg border border-blue-100">
                      <div>
                        <p className="text-sm text-gray-500 mb-1">Bank Pengirim</p>
                        <div className="flex items-center gap-2">
                          <Building className="w-4 h-4 text-gray-400" />
                          <p className="font-medium">{extendedTransaction.bank}</p>
                        </div>
                      </div>
                      <div>
                        <p className="text-sm text-gray-500 mb-1">Nomor Rekening</p>
                        <p className="font-medium font-mono">{extendedTransaction.accountNumber}</p>
                      </div>
                      <div className="col-span-2">
                        <p className="text-sm text-gray-500 mb-1">Payment ID Pengirim</p>
                        {onOpenUserProfile ? (
                          <button
                            onClick={() => onOpenUserProfile(extendedTransaction.sourcePaymentId)}
                            className="font-medium font-mono text-[#139EF6] hover:text-[#0f7ec4] flex items-center gap-2 group transition-colors"
                          >
                            {extendedTransaction.sourcePaymentId}
                            <ExternalLink className="w-4 h-4 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
                          </button>
                        ) : (
                          <p className="font-medium font-mono">{extendedTransaction.sourcePaymentId}</p>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Destination Account Details */}
                  <div>
                    <div className="flex items-center gap-2 mb-4">
                      <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                      <h4 className="font-medium text-gray-900">Tujuan Transfer</h4>
                    </div>
                    <div className="grid grid-cols-2 gap-4 bg-green-50/50 p-4 rounded-lg border border-green-100">
                      <div>
                        <p className="text-sm text-gray-500 mb-1">Bank Penerima</p>
                        <div className="flex items-center gap-2">
                          <Building className="w-4 h-4 text-gray-400" />
                          <p className="font-medium">{extendedTransaction.recipientBank}</p>
                        </div>
                      </div>
                      <div>
                        <p className="text-sm text-gray-500 mb-1">Nomor Rekening</p>
                        <p className="font-medium font-mono">{extendedTransaction.recipientAccount}</p>
                      </div>
                      <div className="col-span-2">
                        <p className="text-sm text-gray-500 mb-1">Payment ID Penerima</p>
                        {onOpenUserProfile ? (
                          <button
                            onClick={() => onOpenUserProfile(extendedTransaction.destinationPaymentId)}
                            className="font-medium font-mono text-[#139EF6] hover:text-[#0f7ec4] flex items-center gap-2 group transition-colors"
                          >
                            {extendedTransaction.destinationPaymentId}
                            <ExternalLink className="w-4 h-4 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
                          </button>
                        ) : (
                          <p className="font-medium font-mono">{extendedTransaction.destinationPaymentId}</p>
                        )}
                      </div>
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
                    {extendedTransaction.analysisDetails.patternMatching}
                  </p>
                </div>

                <div>
                  <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                    <Users className="w-4 h-4" />
                    Analisis Perilaku
                  </h4>
                  <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 p-3 rounded-lg">
                    {extendedTransaction.analysisDetails.behaviorAnalysis}
                  </p>
                </div>

                <div>
                  <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                    <Eye className="w-4 h-4" />
                    Analisis Jaringan
                  </h4>
                  <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 p-3 rounded-lg">
                    {extendedTransaction.analysisDetails.networkAnalysis}
                  </p>
                </div>

                <div>
                  <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                    <Flag className="w-4 h-4" />
                    Rekomendasi Tindakan
                  </h4>
                  <div className={`p-4 rounded-lg border-l-4 ${
                    extendedTransaction.status === 'blocked' 
                      ? 'bg-red-50 border-red-500' 
                      : extendedTransaction.status === 'flagged'
                      ? 'bg-yellow-50 border-yellow-500'
                      : 'bg-green-50 border-green-500'
                  }`}>
                    <p className="text-sm text-gray-700 font-medium leading-relaxed">
                      {extendedTransaction.analysisDetails.recommendation}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Technical Details */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Activity className="w-5 h-5 text-gray-600" />
                  Detail Teknis
                </CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-2 gap-4">
                <div className="space-y-3">
                  <div>
                    <p className="text-sm text-gray-500">IP Address</p>
                    <p className="font-mono text-sm">{extendedTransaction.ipAddress}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Lokasi</p>
                    <div className="flex items-center gap-2">
                      <MapPin className="w-4 h-4 text-gray-400" />
                      <p className="text-sm">{extendedTransaction.location}</p>
                    </div>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Device ID</p>
                    <p className="font-mono text-xs">{extendedTransaction.deviceId}</p>
                  </div>
                </div>
                
                <div className="space-y-3">
                  <div>
                    <p className="text-sm text-gray-500">Session ID</p>
                    <p className="font-mono text-xs">{extendedTransaction.sessionId}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Reference Number</p>
                    <p className="font-mono text-sm">{extendedTransaction.referenceNumber}</p>
                  </div>
                  {extendedTransaction.merchantId && (
                    <div>
                      <p className="text-sm text-gray-500">Merchant ID</p>
                      <p className="font-mono text-sm">{extendedTransaction.merchantId}</p>
                    </div>
                  )}
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
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}