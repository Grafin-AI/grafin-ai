import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { motion } from 'motion/react';
import { TrendingUp, Calendar } from 'lucide-react';
import { useState } from 'react';

const transactionData = {
  '24h': [
    { time: '00:00', volume: 1250000000, count: 234, label: '12 AM' },
    { time: '02:00', volume: 890000000, count: 167, label: '2 AM' },
    { time: '04:00', volume: 650000000, count: 123, label: '4 AM' },
    { time: '06:00', volume: 1800000000, count: 345, label: '6 AM' },
    { time: '08:00', volume: 4200000000, count: 786, label: '8 AM' },
    { time: '10:00', volume: 5900000000, count: 1024, label: '10 AM' },
    { time: '12:00', volume: 7200000000, count: 1234, label: '12 PM' },
    { time: '14:00', volume: 8100000000, count: 1456, label: '2 PM' },
    { time: '16:00', volume: 6800000000, count: 1189, label: '4 PM' },
    { time: '18:00', volume: 5200000000, count: 967, label: '6 PM' },
    { time: '20:00', volume: 3400000000, count: 634, label: '8 PM' },
    { time: '22:00', volume: 2100000000, count: 398, label: '10 PM' }
  ],
  'weekly': [
    { time: 'Mon', volume: 89500000000, count: 15234, label: 'Monday' },
    { time: 'Tue', volume: 124300000000, count: 18456, label: 'Tuesday' },
    { time: 'Wed', volume: 156700000000, count: 22134, label: 'Wednesday' },
    { time: 'Thu', volume: 178900000000, count: 25678, label: 'Thursday' },
    { time: 'Fri', volume: 201200000000, count: 28945, label: 'Friday' },
    { time: 'Sat', volume: 143600000000, count: 19867, label: 'Saturday' },
    { time: 'Sun', volume: 98700000000, count: 13445, label: 'Sunday' }
  ],
  'monthly': [
    { time: 'Jan', volume: 2345000000000, count: 456789, label: 'January' },
    { time: 'Feb', volume: 2156000000000, count: 423567, label: 'February' },
    { time: 'Mar', volume: 2789000000000, count: 534678, label: 'March' },
    { time: 'Apr', volume: 2456000000000, count: 467890, label: 'April' },
    { time: 'May', volume: 2678000000000, count: 512345, label: 'May' },
    { time: 'Jun', volume: 2534000000000, count: 489012, label: 'June' },
    { time: 'Jul', volume: 2890000000000, count: 567234, label: 'July' },
    { time: 'Aug', volume: 2734000000000, count: 523456, label: 'August' },
    { time: 'Sep', volume: 2567000000000, count: 498765, label: 'September' },
    { time: 'Oct', volume: 2823000000000, count: 556789, label: 'October' },
    { time: 'Nov', volume: 2645000000000, count: 501234, label: 'November' },
    { time: 'Dec', volume: 2912000000000, count: 578901, label: 'December' }
  ],
  'yearly': [
    { time: '2019', volume: 24567000000000, count: 4567890, label: '2019' },
    { time: '2020', volume: 21234000000000, count: 3945678, label: '2020' },
    { time: '2021', volume: 28901000000000, count: 5234567, label: '2021' },
    { time: '2022', volume: 32456000000000, count: 5789012, label: '2022' },
    { time: '2023', volume: 36789000000000, count: 6345678, label: '2023' },
    { time: '2024', volume: 39234000000000, count: 6789012, label: '2024' }
  ]
};

const formatAmount = (amount: number) => {
  if (amount >= 1000000000) {
    return `${(amount / 1000000000).toFixed(1)}B`;
  }
  return `${(amount / 1000000).toFixed(0)}M`;
};

const formatFullAmount = (amount: number) => {
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(amount);
};

type PeriodType = '24h' | 'weekly' | 'monthly' | 'yearly';

const periodLabels = {
  '24h': '24H Overview',
  'weekly': 'Weekly Overview',
  'monthly': 'Monthly Overview',
  'yearly': 'Yearly Overview'
};

export function TransactionVolume() {
  const [selectedPeriod, setSelectedPeriod] = useState<PeriodType>('24h');
  const currentData = transactionData[selectedPeriod];

  return (
    <Card>
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-garda-dark-blue" />
              Transaction Volume Trends
              <Badge variant="secondary" className="ml-2">
                {periodLabels[selectedPeriod]}
              </Badge>
            </CardTitle>
            <p className="text-sm text-gray-500 mt-1">
              Real-time transaction volume across all connected banks
            </p>
          </div>
          
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-gray-500" />
            <Select value={selectedPeriod} onValueChange={(value: PeriodType) => setSelectedPeriod(value)}>
              <SelectTrigger className="w-32 h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="24h" className="text-xs">24 Hours</SelectItem>
                <SelectItem value="weekly" className="text-xs">Weekly</SelectItem>
                <SelectItem value="monthly" className="text-xs">Monthly</SelectItem>
                <SelectItem value="yearly" className="text-xs">Yearly</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

      </CardHeader>

      <CardContent>
        <motion.div
          key={selectedPeriod}
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.6 }}
        >
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart 
              data={currentData}
              margin={{ top: 10, right: 30, left: 20, bottom: 5 }}
            >
              <defs>
                <linearGradient id="volumeGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#139EF6" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#139EF6" stopOpacity={0.05}/>
                </linearGradient>
                <linearGradient id="strokeGradient" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#139EF6"/>
                  <stop offset="50%" stopColor="#2BB0F6"/>
                  <stop offset="100%" stopColor="#43C2F7"/>
                </linearGradient>
              </defs>
              
              <CartesianGrid 
                strokeDasharray="3 3" 
                stroke="#e5e7eb" 
                opacity={0.4}
                vertical={false}
              />
              
              <XAxis 
                dataKey="label" 
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 11, fill: '#6b7280' }}
                dy={10}
                angle={selectedPeriod === 'monthly' ? -45 : 0}
                textAnchor={selectedPeriod === 'monthly' ? 'end' : 'middle'}
                height={selectedPeriod === 'monthly' ? 60 : 30}
              />
              
              <YAxis 
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 11, fill: '#6b7280' }}
                tickFormatter={(value) => formatAmount(value)}
                dx={-10}
              />
              
              <Tooltip
                contentStyle={{
                  backgroundColor: '#ffffff',
                  border: '1px solid #e5e7eb',
                  borderRadius: '12px',
                  boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)',
                  fontSize: '12px',
                  padding: '12px'
                }}
                formatter={(value: any, name) => [
                  formatFullAmount(Number(value)),
                  'Transaction Volume'
                ]}
                labelFormatter={(label) => {
                  const periodPrefix = {
                    '24h': 'Time: ',
                    'weekly': 'Day: ',
                    'monthly': 'Month: ',
                    'yearly': 'Year: '
                  };
                  return `${periodPrefix[selectedPeriod]}${label}`;
                }}
                cursor={{ stroke: '#139EF6', strokeWidth: 1, strokeDasharray: '2 2' }}
              />
              
              <Area 
                type="monotone" 
                dataKey="volume" 
                stroke="url(#strokeGradient)"
                strokeWidth={3}
                fill="url(#volumeGradient)"
                dot={{ r: 4, fill: '#139EF6', strokeWidth: 2, stroke: '#ffffff' }}
                activeDot={{ 
                  r: 6, 
                  fill: '#139EF6', 
                  strokeWidth: 3, 
                  stroke: '#ffffff',
                  style: { filter: 'drop-shadow(0 2px 4px rgba(19, 158, 246, 0.3))' }
                }}
                animationBegin={200}
                animationDuration={1000}
                animationEasing="ease-out"
              />
            </AreaChart>
          </ResponsiveContainer>
        </motion.div>
      </CardContent>
    </Card>
  );
}