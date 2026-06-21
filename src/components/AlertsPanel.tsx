import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { ScrollArea } from './ui/scroll-area';
import { AlertTriangle, Shield, Clock, Bell } from 'lucide-react';

interface Alert {
  id: string;
  type: 'critical' | 'warning' | 'info';
  title: string;
  description: string;
  timestamp: string;
  bank: string;
  amount?: number;
}

const mockAlerts: Alert[] = [
  {
    id: 'ALERT-001',
    type: 'critical',
    title: 'Suspicious High-Value Transaction',
    description: 'Multiple large transfers detected from same account within 5 minutes',
    timestamp: '2 minutes ago',
    bank: 'Bank BCA',
    amount: 50000000
  },
  {
    id: 'ALERT-002',
    type: 'warning',
    title: 'Unusual Location Activity',
    description: 'Transaction from location 1000km from usual activity',
    timestamp: '8 minutes ago',
    bank: 'Bank Mandiri',
    amount: 5000000
  },
  {
    id: 'ALERT-003',
    type: 'critical',
    title: 'Possible Account Takeover',
    description: 'Multiple failed login attempts followed by successful transaction',
    timestamp: '15 minutes ago',
    bank: 'Bank BRI',
    amount: 15000000
  },
  {
    id: 'ALERT-004',
    type: 'info',
    title: 'Model Update Complete',
    description: 'Fraud detection model v2.1.3 deployed successfully',
    timestamp: '1 hour ago',
    bank: 'System'
  },
  {
    id: 'ALERT-005',
    type: 'warning',
    title: 'Velocity Check Triggered',
    description: 'Account exceeded daily transaction limit by 300%',
    timestamp: '2 hours ago',
    bank: 'Bank BNI',
    amount: 25000000
  }
];

function AlertItem({ alert }: { alert: Alert }) {
  const getAlertColor = (type: string) => {
    switch (type) {
      case 'critical': return 'bg-red-100 text-red-800 border-red-200';
      case 'warning': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'info': return 'text-blue-800 border-blue-200' style={{backgroundColor: 'rgba(19, 158, 246, 0.1)'}};
      default: return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const getIcon = (type: string) => {
    switch (type) {
      case 'critical': return <AlertTriangle className="w-4 h-4 text-red-600" />;
      case 'warning': return <Shield className="w-4 h-4 text-yellow-600" />;
      case 'info': return <Bell className="w-4 h-4" style={{color: '#139EF6'}} />;
      default: return <Bell className="w-4 h-4 text-gray-600" />;
    }
  };

  const formatAmount = (amount: number) => {
    return new Intl.NumberFormat('id-ID', {
      style: 'currency',
      currency: 'IDR',
      notation: 'compact'
    }).format(amount);
  };

  return (
    <div className={`p-4 rounded-lg border ${getAlertColor(alert.type)} mb-3`}>
      <div className="flex items-start gap-3">
        <div className="mt-0.5">
          {getIcon(alert.type)}
        </div>
        
        <div className="flex-1">
          <div className="flex items-center justify-between mb-1">
            <h4 className="text-sm font-medium">{alert.title}</h4>
            <Badge variant="outline" className="text-xs">
              {alert.type}
            </Badge>
          </div>
          
          <p className="text-xs text-gray-600 mb-2">{alert.description}</p>
          
          <div className="flex items-center justify-between text-xs text-gray-500">
            <div className="flex items-center gap-4">
              <span>{alert.bank}</span>
              {alert.amount && (
                <span className="font-medium">{formatAmount(alert.amount)}</span>
              )}
            </div>
            
            <div className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {alert.timestamp}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function AlertsPanel() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bell className="w-5 h-5" />
          Recent Alerts
          <Badge className="bg-red-500 hover:bg-red-500 text-white">
            {mockAlerts.filter(alert => alert.type === 'critical').length}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-80">
          {mockAlerts.map((alert) => (
            <AlertItem key={alert.id} alert={alert} />
          ))}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}