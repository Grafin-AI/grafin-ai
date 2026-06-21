import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { TrendingUp, TrendingDown, Shield, AlertTriangle, CreditCard, Eye } from 'lucide-react';

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

export function MetricsOverview() {
  const metrics = [
    {
      title: "Total Transactions",
      value: "2,458,392",
      change: "+12.5%",
      trend: "up" as const,
      icon: <CreditCard className="w-4 h-4" style={{color: '#139EF6'}} />,
      color: "bg-blue-50"
    },
    {
      title: "Fraud Detected",
      value: "1,247",
      change: "-8.2%",
      trend: "down" as const,
      icon: <AlertTriangle className="w-4 h-4 text-red-600" />,
      color: "bg-red-100"
    },
    {
      title: "Detection Rate",
      value: "99.94%",
      change: "+0.1%",
      trend: "up" as const,
      icon: <Shield className="w-4 h-4 text-green-600" />,
      color: "bg-green-100"
    },
    {
      title: "Avg Response Time",
      value: "23ms",
      change: "-15.3%",
      trend: "down" as const,
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