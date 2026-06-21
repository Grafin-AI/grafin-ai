import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';

const fraudDistributionData = [
  { name: 'Low Risk (0-30%)', value: 85.2, color: '#10b981' },
  { name: 'Medium Risk (31-70%)', value: 12.1, color: '#f59e0b' },
  { name: 'High Risk (71-100%)', value: 2.7, color: '#ef4444' }
];

const bankFraudData = [
  { bank: 'BCA', fraudCount: 145 },
  { bank: 'Mandiri', fraudCount: 230 },
  { bank: 'BRI', fraudCount: 312 },
  { bank: 'BNI', fraudCount: 187 },
  { bank: 'CIMB', fraudCount: 98 },
  { bank: 'Danamon', fraudCount: 156 }
];

const topSuspectedFraudData = [
  { fraudType: 'Bridge CEX', totalAmount: 45200000000, count: 23 },
  { fraudType: 'Mule Account', totalAmount: 38500000000, count: 31 },
  { fraudType: 'Smurfing', totalAmount: 29800000000, count: 45 },
  { fraudType: 'Trade-Based', totalAmount: 22100000000, count: 18 },
  { fraudType: 'Layering', totalAmount: 15600000000, count: 27 },
  { fraudType: 'Card Testing', totalAmount: 8900000000, count: 52 }
];

export function FraudAnalytics() {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Card>
        <CardHeader>
          <CardTitle>Fraud Score Distribution</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={fraudDistributionData}
                cx="50%"
                cy="50%"
                innerRadius={40}
                outerRadius={80}
                paddingAngle={5}
                dataKey="value"
              >
                {fraudDistributionData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => `${value}%`} />
            </PieChart>
          </ResponsiveContainer>
          <div className="mt-4 space-y-2">
            {fraudDistributionData.map((item, index) => (
              <div key={index} className="flex items-center gap-2 text-sm">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.color }}></div>
                <span className="flex-1">{item.name}</span>
                <span>{item.value}%</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Fraud by Bank</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={bankFraudData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="bank" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="fraudCount" fill="var(--garda-dark-blue)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Top Suspected Fraud</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart 
              data={topSuspectedFraudData}
              margin={{ top: 15, right: 15, left: 15, bottom: 50 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" opacity={0.5} />
              <XAxis 
                dataKey="fraudType" 
                tick={{ fontSize: 9, fill: '#6b7280' }} 
                angle={-35}
                textAnchor="end"
                height={45}
                interval={0}
              />
              <YAxis 
                tick={{ fontSize: 10, fill: '#6b7280' }} 
                tickFormatter={(value) => `${(value / 1000000000).toFixed(0)}B`}
                width={35}
              />
              <Tooltip 
                formatter={(value) => [
                  `Rp ${(Number(value) / 1000000000).toFixed(1)}B`, 
                  'Total Amount'
                ]}
                labelFormatter={(label) => `Fraud Type: ${label}`}
                contentStyle={{
                  backgroundColor: '#ffffff',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  fontSize: '12px'
                }}
              />
              <Bar 
                dataKey="totalAmount" 
                fill="#139EF6" 
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}