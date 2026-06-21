import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { MapPin, TrendingUp, TrendingDown } from 'lucide-react';

interface ProvinceData {
  name: string;
  fraudCount: number;
  change: number;
  riskLevel: 'low' | 'medium' | 'high';
}

const provinceData: ProvinceData[] = [
  { name: 'DKI Jakarta', fraudCount: 456, change: 12.3, riskLevel: 'high' },
  { name: 'Jawa Barat', fraudCount: 234, change: -5.2, riskLevel: 'medium' },
  { name: 'Jawa Timur', fraudCount: 189, change: 8.7, riskLevel: 'medium' },
  { name: 'Sumatera Utara', fraudCount: 167, change: 15.1, riskLevel: 'medium' },
  { name: 'Jawa Tengah', fraudCount: 145, change: -2.1, riskLevel: 'medium' },
  { name: 'Bali', fraudCount: 98, change: 22.4, riskLevel: 'low' },
  { name: 'Sumatera Selatan', fraudCount: 87, change: -8.3, riskLevel: 'low' },
  { name: 'Kalimantan Timur', fraudCount: 76, change: 5.6, riskLevel: 'low' },
  { name: 'Sulawesi Selatan', fraudCount: 65, change: -12.7, riskLevel: 'low' },
  { name: 'Riau', fraudCount: 54, change: 18.9, riskLevel: 'low' }
];

function getRiskColor(level: string) {
  switch (level) {
    case 'high': return 'bg-red-100 text-red-800';
    case 'medium': return 'bg-yellow-100 text-yellow-800';
    case 'low': return 'bg-green-100 text-green-800';
    default: return 'bg-gray-100 text-gray-800';
  }
}

export function GeographicMap() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MapPin className="w-5 h-5" />
          Fraud by Province
        </CardTitle>
      </CardHeader>
      <CardContent>
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
      </CardContent>
    </Card>
  );
}