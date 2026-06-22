import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { MapPin, TrendingUp, TrendingDown } from 'lucide-react';
import { Skeleton } from './ui/skeleton';
import { useProvinces } from '../api/queries';

function getRiskColor(level: string) {
  switch (level) {
    case 'high': return 'bg-red-100 text-red-800';
    case 'medium': return 'bg-yellow-100 text-yellow-800';
    case 'low': return 'bg-green-100 text-green-800';
    default: return 'bg-gray-100 text-gray-800';
  }
}

export function GeographicMap() {
  const { data, isLoading, isError } = useProvinces();

  // Map API field names {fraud_count, change_pct, risk_level} → {fraudCount, change, riskLevel}
  const provinceData = data?.provinces.map((p) => ({
    name: p.name,
    fraudCount: p.fraud_count,
    change: p.change_pct,
    riskLevel: p.risk_level,
  })) ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MapPin className="w-5 h-5" />
          Fraud by Province
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : isError ? (
          <p className="text-sm text-gray-500">Unable to load provincial data.</p>
        ) : provinceData.length === 0 ? (
          <p className="text-sm text-gray-500">No provincial data available.</p>
        ) : (
          <div className="space-y-3">
            {provinceData.map((province, index) => (
              <div key={index} className="flex items-center justify-between p-3 rounded-lg border bg-gray-50">
                <div className="flex items-center gap-3">
                  <div className="flex flex-col">
                    <span className="text-sm">{province.name}</span>
                    <Badge className={`text-xs w-fit ${getRiskColor(province.riskLevel)}`}>
                      {province.riskLevel} risk
                    </Badge>
                  </div>
                </div>

                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <div className="text-sm">{province.fraudCount}</div>
                    <div className="text-xs text-gray-500">incidents</div>
                  </div>

                  <div className={`flex items-center gap-1 text-xs ${
                    province.change > 0 ? 'text-red-600' : 'text-green-600'
                  }`}>
                    {province.change > 0 ?
                      <TrendingUp className="w-3 h-3" /> :
                      <TrendingDown className="w-3 h-3" />
                    }
                    {Math.abs(province.change)}%
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
