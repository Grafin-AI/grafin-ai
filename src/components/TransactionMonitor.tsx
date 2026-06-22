import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { ScrollArea } from './ui/scroll-area';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Button } from './ui/button';
import { Skeleton } from './ui/skeleton';
import { Clock, Building, CreditCard, Activity, TrendingUp, Eye, AlertTriangle, CheckCircle } from 'lucide-react';
import { TransactionDetailsModal } from './TransactionDetailsModal';
import { UserProfileDetailsModal } from './UserProfileDetailsModal';
import { useLiveTransactions } from '../api/useLiveTransactions';
import type { LiveItem } from '../api/types';

export function TransactionMonitor() {
  const { items } = useLiveTransactions(100);
  const [selectedTransactionId, setSelectedTransactionId] = useState<number | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'approved': return 'bg-green-100 text-green-800 border-green-200';
      case 'flagged': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'blocked': return 'bg-red-100 text-red-800 border-red-200';
      default: return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const getFraudScoreTextColor = (score: number) => {
    if (score > 0.7) return 'text-red-600';
    if (score > 0.4) return 'text-amber-600';
    return 'text-green-600';
  };

  const formatAmount = (amount: number) => {
    return new Intl.NumberFormat('id-ID', {
      style: 'currency',
      currency: 'IDR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  const formatTime = (surfacedAt: string) => {
    try {
      const date = new Date(surfacedAt);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffSecs = Math.floor(diffMs / 1000);
      if (diffSecs < 60) return `${diffSecs} seconds ago`;
      const diffMins = Math.floor(diffSecs / 60);
      if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
      const diffHrs = Math.floor(diffMins / 60);
      return `${diffHrs} hour${diffHrs > 1 ? 's' : ''} ago`;
    } catch {
      return surfacedAt;
    }
  };

  const handleViewTransaction = (transactionId: number) => {
    setSelectedTransactionId(transactionId);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedTransactionId(null);
  };

  const handleOpenUserProfile = (entityId: string) => {
    setSelectedEntityId(entityId);
    setIsProfileModalOpen(true);
  };

  const handleCloseProfileModal = () => {
    setIsProfileModalOpen(false);
    setSelectedEntityId(null);
  };

  return (
    <>
      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
              Live Transaction Monitor
              <Badge variant="secondary" className="ml-2">
                {items.length} Active
              </Badge>
            </CardTitle>
            <div className="flex items-center gap-4 text-sm text-gray-500">
              <div className="flex items-center gap-1">
                <Activity className="w-4 h-4" />
                Real-time monitoring
              </div>
              <div className="flex items-center gap-1">
                <TrendingUp className="w-4 h-4" />
                Auto-refresh (live WS)
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <ScrollArea className="h-[500px]">
            <Table>
              <TableHeader className="sticky top-0 bg-white border-b">
                <TableRow className="hover:bg-transparent">
                  <TableHead className="w-[140px] pl-6">Transaction ID</TableHead>
                  <TableHead className="w-[180px]">Source Bank &amp; Type</TableHead>
                  <TableHead className="w-[140px]">Amount</TableHead>
                  <TableHead className="w-[130px]">Fraud Score</TableHead>
                  <TableHead className="w-[130px]">Suspected Fraud</TableHead>
                  <TableHead className="w-[120px]">Status</TableHead>
                  <TableHead className="w-[130px]">Timestamp</TableHead>
                  <TableHead className="w-[100px] pr-6">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.length === 0 && (
                  <>
                    {Array.from({ length: 6 }).map((_, i) => (
                      <TableRow key={i}>
                        <TableCell className="pl-6"><Skeleton className="h-4 w-24" /></TableCell>
                        <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                        <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                        <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                        <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                        <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                        <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                        <TableCell className="pr-6"><Skeleton className="h-8 w-16" /></TableCell>
                      </TableRow>
                    ))}
                  </>
                )}
                {items.map((item: LiveItem) => (
                  <TableRow key={item.seq} className="hover:bg-gray-50/50">
                    <TableCell className="pl-6">
                      <div className="flex flex-col">
                        <span className="text-sm font-medium text-gray-900">
                          TXN-{item.transaction_id}
                        </span>
                      </div>
                    </TableCell>

                    <TableCell>
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center gap-1">
                          <Building className="w-3 h-3 text-gray-400" />
                          <span className="text-sm font-medium">{item.bank || '—'}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <CreditCard className="w-3 h-3 text-gray-400" />
                          <span className="text-xs text-gray-500">{item.type || '—'}</span>
                        </div>
                      </div>
                    </TableCell>

                    <TableCell>
                      <div className="text-sm font-medium text-gray-900">
                        {formatAmount(item.amount)}
                      </div>
                    </TableCell>

                    <TableCell>
                      <div className="flex items-center gap-3 min-w-[120px]">
                        <span className={`text-sm font-medium ${getFraudScoreTextColor(item.fraud_score)} min-w-[35px]`}>
                          {Math.round(item.fraud_score * 100)}%
                        </span>
                        <div className="flex-1 bg-gray-200 rounded-full h-2 overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-300 ${
                              item.fraud_score > 0.7
                                ? 'bg-red-500'
                                : item.fraud_score > 0.4
                                ? 'bg-amber-500'
                                : 'bg-green-500'
                            }`}
                            style={{ width: `${Math.max(item.fraud_score * 100, 5)}%` }}
                          />
                        </div>
                      </div>
                    </TableCell>

                    <TableCell>
                      <div className="flex items-center gap-2">
                        {item.typology ? (
                          <>
                            <AlertTriangle className="w-4 h-4 text-red-600" />
                            <Badge
                              variant="outline"
                              className="text-xs bg-red-50 text-red-700 border-red-200"
                            >
                              {item.typology}
                            </Badge>
                          </>
                        ) : (
                          <>
                            <CheckCircle className="w-4 h-4 text-green-600" />
                            <span className="text-xs text-gray-500">None</span>
                          </>
                        )}
                      </div>
                    </TableCell>

                    <TableCell>
                      <Badge
                        className={`text-xs capitalize ${getStatusColor(item.status)}`}
                      >
                        {item.status}
                      </Badge>
                    </TableCell>

                    <TableCell>
                      <div className="flex items-center gap-1 text-xs text-gray-500">
                        <Clock className="w-3 h-3" />
                        {formatTime(item.surfaced_at)}
                      </div>
                    </TableCell>

                    <TableCell className="pr-6">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleViewTransaction(item.transaction_id)}
                        className="h-8 px-3 text-xs"
                      >
                        <Eye className="w-3 h-3 mr-1" />
                        View
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        </CardContent>
      </Card>

      {/* Transaction Details Modal */}
      <TransactionDetailsModal
        transactionId={selectedTransactionId}
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        onOpenUserProfile={handleOpenUserProfile}
      />

      {/* User Profile Details Modal */}
      <UserProfileDetailsModal
        entityId={selectedEntityId}
        isOpen={isProfileModalOpen}
        onClose={handleCloseProfileModal}
      />
    </>
  );
}
