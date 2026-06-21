import * as React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { Badge } from './ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Separator } from './ui/separator';
import { ScrollArea } from './ui/scroll-area';
import { Button } from './ui/button';
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
  CreditCard,
  Eye,
  EyeOff,
  BarChart3,
  Calendar,
  Hash
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';

interface RiskProfile {
  id: string;
  paymentId: string;
  actualPaymentId?: string;
  entityType: 'Individual' | 'Company';
  riskLevel: 'Low' | 'Medium' | 'High';
  riskScore: number;
  totalTransactions: number;
  flaggedTransactions: number;
  lastActivity: string;
  accountAge: string;
}

interface ExtendedRiskProfile extends RiskProfile {
  registrationDate: string;
  kycStatus: string;
  primaryBank: string;
  linkedAccounts: number;
  activeDevices: number;
  riskFactors: string[];
  transactionPattern: {
    weekday: number;
    weekend: number;
    nighttime: number;
  };
  monthlyActivity: Array<{ month: string; transactions: number; flagged: number }>;
  riskHistory: Array<{ month: string; score: number }>;
  analysisDetails: {
    behaviorAnalysis: string;
    networkAnalysis: string;
    patternAnalysis: string;
    recommendation: string;
  };
}

interface UserProfileDetailsModalProps {
  profile: RiskProfile | null;
  isOpen: boolean;
  onClose: () => void;
}

const generateExtendedProfileData = (profile: RiskProfile): ExtendedRiskProfile => {
  const riskAnalysisTemplates = {
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

  const analysis = riskAnalysisTemplates[profile.riskLevel];

  const monthlyActivity = [
    { month: 'Apr', transactions: Math.floor(profile.totalTransactions / 6), flagged: Math.floor(profile.flaggedTransactions / 6) },
    { month: 'May', transactions: Math.floor(profile.totalTransactions / 5.5), flagged: Math.floor(profile.flaggedTransactions / 5) },
    { month: 'Jun', transactions: Math.floor(profile.totalTransactions / 5.2), flagged: Math.floor(profile.flaggedTransactions / 4.5) },
    { month: 'Jul', transactions: Math.floor(profile.totalTransactions / 5), flagged: Math.floor(profile.flaggedTransactions / 4) },
    { month: 'Aug', transactions: Math.floor(profile.totalTransactions / 4.8), flagged: profile.flaggedTransactions }
  ];

  const riskHistory = [
    { month: 'Apr', score: Math.max(profile.riskScore - 25, 10) },
    { month: 'May', score: Math.max(profile.riskScore - 18, 15) },
    { month: 'Jun', score: Math.max(profile.riskScore - 12, 20) },
    { month: 'Jul', score: Math.max(profile.riskScore - 6, 25) },
    { month: 'Aug', score: profile.riskScore }
  ];

  const riskFactorsByLevel = {
    'High': ['High Transaction Velocity', 'Unusual Timing Pattern', 'Network Risk', 'Geographic Anomaly', 'Rapid Fund Movement', 'Multiple Linked Accounts'],
    'Medium': ['Moderate Velocity', 'Minor Pattern Deviation', 'Threshold Proximity'],
    'Low': ['Consistent Behavior', 'Verified Profile']
  };

  return {
    ...profile,
    registrationDate: new Date(Date.now() - parseInt(profile.accountAge) * 365 * 24 * 60 * 60 * 1000).toLocaleDateString('id-ID'),
    kycStatus: profile.riskLevel === 'High' ? 'Enhanced Review Required' : profile.riskLevel === 'Medium' ? 'Verified - Needs Update' : 'Fully Verified',
    primaryBank: ['Bank BCA', 'Bank Mandiri', 'Bank BRI', 'Bank BNI'][Math.floor(Math.random() * 4)],
    linkedAccounts: profile.riskLevel === 'High' ? Math.floor(Math.random() * 8) + 5 : Math.floor(Math.random() * 3) + 1,
    activeDevices: profile.riskLevel === 'High' ? Math.floor(Math.random() * 5) + 3 : Math.floor(Math.random() * 2) + 1,
    riskFactors: riskFactorsByLevel[profile.riskLevel],
    transactionPattern: {
      weekday: profile.riskLevel === 'High' ? 45 : 75,
      weekend: profile.riskLevel === 'High' ? 35 : 20,
      nighttime: profile.riskLevel === 'High' ? 20 : 5
    },
    monthlyActivity,
    riskHistory,
    analysisDetails: analysis
  };
};

export function UserProfileDetailsModal({ profile, isOpen, onClose }: UserProfileDetailsModalProps) {
  if (!profile) return null;

  const [showActualPaymentId, setShowActualPaymentId] = React.useState(false);

  const extendedProfile = React.useMemo(() => generateExtendedProfileData(profile), [profile]);

  const getRiskLevelColor = (level: string) => {
    switch (level) {
      case 'High':
        return 'bg-red-100 text-red-800 border-red-200';
      case 'Medium':
        return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'Low':
        return 'bg-green-100 text-green-800 border-green-200';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const getRiskIcon = (level: string) => {
    switch (level) {
      case 'High':
        return <AlertTriangle className="w-4 h-4 text-red-600" />;
      case 'Medium':
        return <Shield className="w-4 h-4 text-yellow-600" />;
      case 'Low':
        return <Shield className="w-4 h-4 text-green-600" />;
      default:
        return <Activity className="w-4 h-4 text-gray-600" />;
    }
  };



  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-7xl sm:max-w-7xl max-h-[90vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              {getRiskIcon(extendedProfile.riskLevel)}
              Detail Profil Risiko - {extendedProfile.paymentId}
            </div>
            <Badge className={`text-xs capitalize ${getRiskLevelColor(extendedProfile.riskLevel)}`}>
              {extendedProfile.riskLevel} Risk
            </Badge>
          </DialogTitle>
          <DialogDescription>
            Analisis lengkap profil risiko dan pola transaksi untuk akun {extendedProfile.paymentId}
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-[calc(90vh-80px)]">
          <div className="space-y-6 pr-4">
            {/* Profile Overview and Risk Assessment - Side by Side */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Profile Overview */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    {extendedProfile.entityType === 'Company' ? (
                      <Building2 className="w-5 h-5 text-blue-600" />
                    ) : (
                      <UserIcon className="w-5 h-5 text-blue-600" />
                    )}
                    Informasi Profil
                  </CardTitle>
                </CardHeader>
                <CardContent className="grid grid-cols-2 gap-4">
                  <div className="space-y-3">
                    <div>
                      <p className="text-sm text-gray-500 mb-1">Payment ID</p>
                      <div className="flex items-center gap-2">
                        <code className="font-mono text-sm bg-gray-100 px-2 py-1 rounded">
                          {showActualPaymentId ? (profile.actualPaymentId || 'PAY-2024-ID-8372916450') : extendedProfile.paymentId}
                        </code>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 w-6 p-0 hover:bg-gray-100"
                          onClick={() => setShowActualPaymentId(!showActualPaymentId)}
                        >
                          {showActualPaymentId ? (
                            <EyeOff className="w-4 h-4 text-gray-500" />
                          ) : (
                            <Eye className="w-4 h-4 text-gray-500" />
                          )}
                        </Button>
                      </div>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Tipe Entitas</p>
                      <Badge variant="outline" className="gap-1">
                        {extendedProfile.entityType === 'Company' ? (
                          <Building2 className="w-3 h-3" />
                        ) : (
                          <UserIcon className="w-3 h-3" />
                        )}
                        {extendedProfile.entityType}
                      </Badge>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Status KYC</p>
                      <p className="font-medium">{extendedProfile.kycStatus}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Linked Accounts</p>
                      <p className="font-medium">{extendedProfile.linkedAccounts} accounts</p>
                    </div>
                  </div>
                  
                  <div className="space-y-3">
                    <div>
                      <p className="text-sm text-gray-500">Tanggal Registrasi</p>
                      <div className="flex items-center gap-2">
                        <Calendar className="w-4 h-4 text-gray-400" />
                        <p className="font-medium">{extendedProfile.registrationDate}</p>
                      </div>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Usia Akun</p>
                      <p className="font-medium">{extendedProfile.accountAge}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Bank Utama</p>
                      <p className="font-medium">{extendedProfile.primaryBank}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Active Devices</p>
                      <p className="font-medium">{extendedProfile.activeDevices} devices</p>
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
                        extendedProfile.riskLevel === 'High' ? 'text-red-600' :
                        extendedProfile.riskLevel === 'Medium' ? 'text-yellow-600' : 'text-green-600'
                      }`} />
                      Penilaian Risiko
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`text-2xl font-bold ${
                        extendedProfile.riskScore > 70 ? 'text-red-600' :
                        extendedProfile.riskScore > 40 ? 'text-amber-600' : 'text-green-600'
                      }`}>
                        {Math.round(extendedProfile.riskScore)}%
                      </span>
                      <div className="w-32 bg-gray-200 rounded-full h-3">
                        <div 
                          className={`h-3 rounded-full ${
                            extendedProfile.riskScore > 70 
                              ? 'bg-red-500' 
                              : extendedProfile.riskScore > 40 
                              ? 'bg-amber-500' 
                              : 'bg-green-500'
                          }`}
                          style={{ width: `${extendedProfile.riskScore}%` }}
                        />
                      </div>
                    </div>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <p className="text-sm text-gray-500 mb-2">Faktor Risiko</p>
                    <div className="flex flex-wrap gap-2">
                      {extendedProfile.riskFactors.map((factor, index) => (
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
                      <p className="text-xl font-bold">{extendedProfile.totalTransactions.toLocaleString('en-US')}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Transaksi Flagged</p>
                      <p className="text-xl font-bold text-red-600">{extendedProfile.flaggedTransactions}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Flag Rate</p>
                      <p className="text-xl font-bold">
                        {((extendedProfile.flaggedTransactions / extendedProfile.totalTransactions) * 100).toFixed(1)}%
                      </p>
                    </div>
                  </div>

                </CardContent>
              </Card>
            </div>

            {/* Activity and Risk Score History */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Monthly Activity */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="w-5 h-5 text-blue-600" />
                    Aktivitas Bulanan
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={extendedProfile.monthlyActivity}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                      <XAxis dataKey="month" stroke="#6B7280" style={{ fontSize: '12px' }} />
                      <YAxis stroke="#6B7280" style={{ fontSize: '12px' }} />
                      <Tooltip />
                      <Bar dataKey="transactions" fill="#139EF6" name="Total" />
                      <Bar dataKey="flagged" fill="#EF4444" name="Flagged" />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              {/* Risk Score History */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="w-5 h-5 text-blue-600" />
                    Riwayat Risk Score
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={extendedProfile.riskHistory}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                      <XAxis dataKey="month" stroke="#6B7280" style={{ fontSize: '12px' }} />
                      <YAxis stroke="#6B7280" style={{ fontSize: '12px' }} />
                      <Tooltip />
                      <Line type="monotone" dataKey="score" stroke="#EF4444" strokeWidth={2} name="Risk Score" />
                    </LineChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </div>

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
                      {extendedProfile.analysisDetails.behaviorAnalysis}
                    </p>
                  </div>

                  <div>
                    <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                      <TrendingUp className="w-4 h-4" />
                      Analisis Jaringan
                    </h4>
                    <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 p-3 rounded-lg">
                      {extendedProfile.analysisDetails.networkAnalysis}
                    </p>
                  </div>
                </div>

                <Separator />

                <div>
                  <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                    <BarChart3 className="w-4 h-4" />
                    Analisis Pola Transaksi
                  </h4>
                  <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 p-3 rounded-lg">
                    {extendedProfile.analysisDetails.patternAnalysis}
                  </p>
                </div>

                <Separator />

                <div>
                  <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                    <Flag className="w-4 h-4" />
                    Rekomendasi Tindakan
                  </h4>
                  <div className={`p-4 rounded-lg border-l-4 ${
                    extendedProfile.riskLevel === 'High' 
                      ? 'bg-red-50 border-red-500' 
                      : extendedProfile.riskLevel === 'Medium'
                      ? 'bg-yellow-50 border-yellow-500'
                      : 'bg-green-50 border-green-500'
                  }`}>
                    <p className="text-sm text-gray-700 font-medium leading-relaxed">
                      {extendedProfile.analysisDetails.recommendation}
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
                    <p className="text-sm text-gray-500">Profile ID</p>
                    <p className="font-mono text-sm">{extendedProfile.id}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Monitoring Status</p>
                    <Badge variant={extendedProfile.riskLevel === 'High' ? 'destructive' : 'secondary'}>
                      {extendedProfile.riskLevel === 'High' ? 'Active Monitoring' : 'Standard Monitoring'}
                    </Badge>
                  </div>
                </div>
                
                <div className="space-y-3">
                  <div>
                    <p className="text-sm text-gray-500">Last Activity</p>
                    <div className="flex items-center gap-2">
                      <Clock className="w-4 h-4 text-gray-400" />
                      <p className="text-sm">{extendedProfile.lastActivity}</p>
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
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
