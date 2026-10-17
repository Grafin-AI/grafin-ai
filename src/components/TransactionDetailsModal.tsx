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
import { useTransactionDetail, useTransactionExplanation } from '../api/queries';
import type { TransactionDetail } from '../api/types';

interface TransactionDetailsModalProps {
  transactionId: number | null;
  isOpen: boolean;
  onClose: () => void;
  onOpenUserProfile?: (entityId: string) => void;
}

type Side = 'from' | 'to';

function PartyBlock({ txn, side, onOpenUserProfile }: {
  txn: TransactionDetail;
  side: Side;
  onOpenUserProfile?: (entityId: string) => void;
}) {
  const isFrom = side === 'from';
  const bankCode = isFrom ? txn.from_bank : txn.to_bank;
  const bankName = isFrom ? txn.from_bank_name : txn.to_bank_name;
  const account = isFrom ? txn.from_account : txn.to_account;
  const entityId = isFrom ? txn.from_entity_id : txn.to_entity_id;
  const entityName = isFrom ? txn.from_entity_name : txn.to_entity_name;
  const label = isFrom ? 'Pengirim' : 'Penerima';

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <div className={`w-2 h-2 rounded-full ${isFrom ? 'bg-blue-500' : 'bg-purple-500'}`}></div>
        <h4 className="font-medium text-gray-900">{label}</h4>
      </div>
      <div className={`grid grid-cols-2 gap-4 p-4 rounded-lg border ${
        isFrom ? 'bg-blue-50/50 border-blue-100' : 'bg-purple-50/50 border-purple-100'
      }`}>
        <div>
          <p className="text-sm text-gray-500 mb-1">Bank</p>
          <div className="flex items-center gap-2">
            <Building className="w-4 h-4 text-gray-400" />
            <p className="font-medium">{bankName || bankCode || '—'}</p>
          </div>
        </div>
        <div>
          <p className="text-sm text-gray-500 mb-1">Rekening</p>
          <p className="font-medium font-mono">{account || '—'}</p>
        </div>
        <div className="col-span-2">
          <p className="text-sm text-gray-500 mb-1">Nama Entitas</p>
          <p className="font-medium">{entityName || '—'}</p>
        </div>
        {onOpenUserProfile && (
          <div className="col-span-2">
            <p className="text-sm text-gray-500 mb-1">Entity ID</p>
            <button
              type="button"
              aria-label={`Buka profil ${label.toLowerCase()}`}
              disabled={!entityId}
              onClick={() => entityId && onOpenUserProfile(entityId)}
              className="font-medium font-mono text-[#139EF6] hover:text-[#0f7ec4] disabled:text-gray-400 disabled:cursor-not-allowed flex items-center gap-2 group transition-colors text-sm"
            >
              {entityId ?? 'Tidak tersedia'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

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

  const {
    data: explanation,
    isLoading: explanationLoading,
    isError: explanationError,
  } = useTransactionExplanation(transactionId, isOpen);

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
                        {explanationLoading ? (
                          <Skeleton className="h-5 w-40" />
                        ) : explanationError ? (
                          <span className="text-xs text-gray-500">Faktor risiko tidak tersedia</span>
                        ) : explanation && explanation.risk_factors.length > 0 ? (
                          explanation.risk_factors.map((factor) => (
                            <Badge key={factor.code} variant="secondary" className="text-xs" title={factor.detail}>
                              {factor.label}
                            </Badge>
                          ))
                        ) : (
                          <span className="text-xs text-gray-500">Tidak ada faktor risiko menonjol</span>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Sender / Receiver */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <ArrowRight className="w-5 h-5 text-[#139EF6]" />
                    Detail Pengirim &amp; Penerima
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <PartyBlock txn={txn} side="from" onOpenUserProfile={onOpenUserProfile} />
                    <PartyBlock txn={txn} side="to" onOpenUserProfile={onOpenUserProfile} />
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
                  {explanation && (
                    <p className="text-xs text-gray-500">
                      {explanation.source === 'llm'
                        ? `Dihasilkan oleh ${explanation.model ?? 'LLM'}`
                        : 'Ringkasan berbasis aturan'}
                      {explanation.generated_at && ` · ${new Date(explanation.generated_at).toLocaleString('id-ID')}`}
                    </p>
                  )}
                </CardHeader>
                {explanationLoading ? (
                  <CardContent className="space-y-3">
                    <p className="text-sm text-gray-500">Menganalisis transaksi…</p>
                    <Skeleton className="h-16 w-full" />
                    <Skeleton className="h-16 w-full" />
                  </CardContent>
                ) : explanationError || !explanation ? (
                  <CardContent>
                    <p className="text-sm text-gray-500">Analisis belum tersedia untuk transaksi ini.</p>
                  </CardContent>
                ) : (
                <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                      <Activity className="w-4 h-4" />
                      Pattern Matching
                    </h4>
                    <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 p-3 rounded-lg">
                      {explanation.pattern_matching}
                    </p>
                  </div>

                  <div>
                    <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                      <Users className="w-4 h-4" />
                      Analisis Perilaku
                    </h4>
                    <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 p-3 rounded-lg">
                      {explanation.behavior_analysis}
                    </p>
                  </div>

                  <div>
                    <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                      <Eye className="w-4 h-4" />
                      Analisis Jaringan
                    </h4>
                    <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 p-3 rounded-lg">
                      {explanation.network_analysis}
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
                        {explanation.recommendation}
                      </p>
                    </div>
                  </div>
                </CardContent>
                )}
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
