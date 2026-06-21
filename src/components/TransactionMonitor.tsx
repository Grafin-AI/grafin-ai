import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { ScrollArea } from './ui/scroll-area';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Progress } from './ui/progress';
import { Button } from './ui/button';
import { Clock, Building, CreditCard, Activity, TrendingUp, Eye, AlertTriangle, CheckCircle } from 'lucide-react';
import { TransactionDetailsModal } from './TransactionDetailsModal';
import { UserProfileDetailsModal } from './UserProfileDetailsModal';

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

const mockTransactions: Transaction[] = [
  {
    id: "TXN-001",
    bank: "Bank BCA",
    amount: 15000000,
    fraudScore: 0.95,
    timestamp: "2 seconds ago",
    status: "blocked",
    type: "Transfer",
    suspectedFraudType: "Bridge CEX Withdrawal"
  },
  {
    id: "TXN-002",
    bank: "Bank Mandiri",
    amount: 250000,
    fraudScore: 0.15,
    timestamp: "5 seconds ago",
    status: "approved",
    type: "Purchase",
    suspectedFraudType: null
  },
  {
    id: "TXN-003",
    bank: "Bank BRI",
    amount: 5000000,
    fraudScore: 0.78,
    timestamp: "8 seconds ago",
    status: "flagged",
    type: "Withdrawal",
    suspectedFraudType: "Smurfing"
  },
  {
    id: "TXN-004",
    bank: "Bank BNI",
    amount: 150000,
    fraudScore: 0.05,
    timestamp: "12 seconds ago",
    status: "approved",
    type: "Purchase",
    suspectedFraudType: null
  },
  {
    id: "TXN-005",
    bank: "Bank CIMB",
    amount: 8500000,
    fraudScore: 0.45,
    timestamp: "18 seconds ago",
    status: "approved",
    type: "Transfer",
    suspectedFraudType: null
  },
  {
    id: "TXN-006",
    bank: "Bank Danamon",
    amount: 750000,
    fraudScore: 0.25,
    timestamp: "25 seconds ago",
    status: "approved",
    type: "Purchase",
    suspectedFraudType: null
  },
  {
    id: "TXN-007",
    bank: "Bank BTN",
    amount: 2500000,
    fraudScore: 0.12,
    timestamp: "32 seconds ago",
    status: "approved",
    type: "Transfer",
    suspectedFraudType: null
  },
  {
    id: "TXN-008",
    bank: "Bank Permata",
    amount: 12000000,
    fraudScore: 0.89,
    timestamp: "45 seconds ago",
    status: "flagged",
    type: "Withdrawal",
    suspectedFraudType: "Mule Account"
  },
  {
    id: "TXN-009",
    bank: "Bank OCBC",
    amount: 3500000,
    fraudScore: 0.67,
    timestamp: "1 minute ago",
    status: "flagged",
    type: "Transfer",
    suspectedFraudType: "Layering"
  },
  {
    id: "TXN-010",
    bank: "Bank Maybank",
    amount: 890000,
    fraudScore: 0.72,
    timestamp: "1 minute ago",
    status: "blocked",
    type: "Purchase",
    suspectedFraudType: "Card Testing"
  },
  {
    id: "TXN-011",
    bank: "Bank UOB",
    amount: 6700000,
    fraudScore: 0.85,
    timestamp: "2 minutes ago",
    status: "flagged",
    type: "Transfer",
    suspectedFraudType: "Trade-Based Money Laundering"
  },
  {
    id: "TXN-012",
    bank: "Bank Standard Chartered",
    amount: 450000,
    fraudScore: 0.08,
    timestamp: "2 minutes ago",
    status: "approved",
    type: "Purchase",
    suspectedFraudType: null
  }
];

export function TransactionMonitor() {
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedProfile, setSelectedProfile] = useState<any>(null);
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

  const formatTime = (timestamp: string) => {
    return timestamp;
  };

  const handleViewTransaction = (transactionId: string) => {
    const transaction = mockTransactions.find(t => t.id === transactionId);
    if (transaction) {
      setSelectedTransaction(transaction);
      setIsModalOpen(true);
    }
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedTransaction(null);
  };

  const handleOpenUserProfile = (paymentId: string) => {
    // Generate a mock user profile based on payment ID
    const mockProfile = {
      id: `USR-${Math.random().toString(36).substr(2, 6).toUpperCase()}`,
      maskedName: 'A****** S******',
      actualName: 'Ahmad Setiawan',
      paymentId: paymentId.replace('PAY-', '***-'),
      actualPaymentId: paymentId,
      entityType: Math.random() > 0.5 ? 'Individual' : 'Company',
      riskLevel: Math.random() > 0.6 ? 'High' : Math.random() > 0.3 ? 'Medium' : 'Low',
      riskScore: Math.random() * 100,
      totalTransactions: Math.floor(Math.random() * 500) + 50,
      flaggedTransactions: Math.floor(Math.random() * 50),
      totalAmount: Math.floor(Math.random() * 500000000) + 10000000,
      lastActivity: 'Today',
      location: ['Jakarta', 'Surabaya', 'Bandung', 'Medan'][Math.floor(Math.random() * 4)],
      accountAge: `${Math.floor(Math.random() * 36) + 1} months`
    };
    
    setSelectedProfile(mockProfile as any);
    setIsProfileModalOpen(true);
  };

  const handleCloseProfileModal = () => {
    setIsProfileModalOpen(false);
    setSelectedProfile(null);
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
                {mockTransactions.length} Active
              </Badge>
            </CardTitle>
            <div className="flex items-center gap-4 text-sm text-gray-500">
              <div className="flex items-center gap-1">
                <Activity className="w-4 h-4" />
                Real-time monitoring
              </div>
              <div className="flex items-center gap-1">
                <TrendingUp className="w-4 h-4" />
                Auto-refresh every 2s
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
                  <TableHead className="w-[180px]">Source Bank & Type</TableHead>
                  <TableHead className="w-[140px]">Amount</TableHead>
                  <TableHead className="w-[130px]">Fraud Score</TableHead>
                  <TableHead className="w-[130px]">Suspected Fraud</TableHead>
                  <TableHead className="w-[120px]">Status</TableHead>
                  <TableHead className="w-[130px]">Timestamp</TableHead>
                  <TableHead className="w-[100px] pr-6">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mockTransactions.map((transaction) => (
                  <TableRow key={transaction.id} className="hover:bg-gray-50/50">
                    <TableCell className="pl-6">
                      <div className="flex flex-col">
                        <span className="text-sm font-medium text-gray-900">{transaction.id}</span>
                      </div>
                    </TableCell>
                    
                    <TableCell>
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center gap-1">
                          <Building className="w-3 h-3 text-gray-400" />
                          <span className="text-sm font-medium">{transaction.bank}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <CreditCard className="w-3 h-3 text-gray-400" />
                          <span className="text-xs text-gray-500">{transaction.type}</span>
                        </div>
                      </div>
                    </TableCell>
                    
                    <TableCell>
                      <div className="text-sm font-medium text-gray-900">
                        {formatAmount(transaction.amount)}
                      </div>
                    </TableCell>
                    
                    <TableCell>
                      <div className="flex items-center gap-3 min-w-[120px]">
                        <span className={`text-sm font-medium ${getFraudScoreTextColor(transaction.fraudScore)} min-w-[35px]`}>
                          {Math.round(transaction.fraudScore * 100)}%
                        </span>
                        <div className="flex-1 bg-gray-200 rounded-full h-2 overflow-hidden">
                          <div 
                            className={`h-full rounded-full transition-all duration-300 ${
                              transaction.fraudScore > 0.7 
                                ? 'bg-red-500' 
                                : transaction.fraudScore > 0.4 
                                ? 'bg-amber-500' 
                                : 'bg-green-500'
                            }`}
                            style={{ width: `${Math.max(transaction.fraudScore * 100, 5)}%` }}
                          />
                        </div>
                      </div>
                    </TableCell>

                    <TableCell>
                      <div className="flex items-center gap-2">
                        {transaction.suspectedFraudType ? (
                          <>
                            <AlertTriangle className="w-4 h-4 text-red-600" />
                            <Badge 
                              variant="outline" 
                              className="text-xs bg-red-50 text-red-700 border-red-200"
                            >
                              {transaction.suspectedFraudType}
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
                        className={`text-xs capitalize ${getStatusColor(transaction.status)}`}
                      >
                        {transaction.status}
                      </Badge>
                    </TableCell>
                    
                    <TableCell>
                      <div className="flex items-center gap-1 text-xs text-gray-500">
                        <Clock className="w-3 h-3" />
                        {formatTime(transaction.timestamp)}
                      </div>
                    </TableCell>

                    <TableCell className="pr-6">
                      <Button 
                        variant="outline" 
                        size="sm"
                        onClick={() => handleViewTransaction(transaction.id)}
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
        transaction={selectedTransaction}
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        onOpenUserProfile={handleOpenUserProfile}
      />

      {/* User Profile Details Modal */}
      <UserProfileDetailsModal 
        profile={selectedProfile}
        isOpen={isProfileModalOpen}
        onClose={handleCloseProfileModal}
      />
    </>
  );
}