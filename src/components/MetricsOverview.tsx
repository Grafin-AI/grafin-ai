import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { TrendingUp, TrendingDown, Shield, AlertTriangle, CreditCard, Eye } from 'lucide-react';
import { Skeleton } from './ui/skeleton';
import { useMetricsOverview } from '../api/queries';

interface MetricCardProps {
  title: string;
  value: string;
  change: string;
  trend: 'up' | 'down';
  icon: React.ReactNode;
  color: string;
}

function MetricCard({ title, value, change, trend, icon, color }: MetricCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
        <div className={`p-2 rounded-lg ${color}`}>
          {icon}
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-2xl mb-1">{value}</div>
        <p className={`text-xs flex items-center gap-1 ${
          trend === 'up' ? 'text-green-600' : 'text-red-600'
        }`}>
          {trend === 'up' ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
          {change} from last hour
        </p>
      </CardContent>
    </Card>
  );
}

function MetricCardSkeleton() {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-8 w-8 rounded-lg" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-8 w-24 mb-2" />
        <Skeleton className="h-3 w-36" />
      </CardContent>
    </Card>
  );
}

const formatIDR = (amount: number) => {
  if (amount >= 1_000_000_000_000) {
    return `Rp ${(amount / 1_000_000_000_000).toFixed(1)}T`;
  }
  if (amount >= 1_000_000_000) {
    return `Rp ${(amount / 1_000_000_000).toFixed(1)}B`;
  }
  if (amount >= 1_000_000) {
    return `Rp ${(amount / 1_000_000).toFixed(1)}M`;
  }
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0 }).format(amount);
};

export function MetricsOverview() {
  const { data, isLoading, isError } = useMetricsOverview();

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <MetricCardSkeleton key={i} />)}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="col-span-4">
          <CardContent className="pt-6">
            <p className="text-sm text-gray-500">Unable to load metrics. Please try again.</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const metrics = [
    {
      title: "Total Transactions",
      value: data.total_transactions.toLocaleString('id-ID'),
      change: `${(data.fraud_rate * 100).toFixed(2)}% fraud rate`,
      trend: "up" as const,
      icon: <CreditCard className="w-4 h-4" style={{color: '#139EF6'}} />,
      color: "bg-blue-50"
    },
    {
      title: "Fraud Detected",
      value: data.flagged.toLocaleString('id-ID'),
      change: `${data.blocked} blocked`,
      trend: "down" as const,
      icon: <AlertTriangle className="w-4 h-4 text-red-600" />,
      color: "bg-red-100"
    },
    {
      title: "Fraud Rate",
      value: `${(data.fraud_rate * 100).toFixed(2)}%`,
      change: `${data.blocked} blocked txns`,
      trend: data.fraud_rate < 0.01 ? "up" as const : "down" as const,
      icon: <Shield className="w-4 h-4 text-green-600" />,
      color: "bg-green-100"
    },
    {
      title: "Total Amount",
      value: formatIDR(data.total_amount),
      change: `${data.flagged} flagged txns`,
      trend: "up" as const,
      icon: <Eye className="w-4 h-4" style={{color: '#139EF6'}} />,
      color: "bg-blue-50"
    }
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {metrics.map((metric, index) => (
        <MetricCard key={index} {...metric} />
      ))}
    </div>
  );
}
