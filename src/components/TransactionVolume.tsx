import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { motion } from 'motion/react';
import { TrendingUp, Calendar } from 'lucide-react';
import { useState } from 'react';
import { Skeleton } from './ui/skeleton';
import { useVolume } from '../api/queries';

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
  const { data, isLoading, isError } = useVolume(selectedPeriod);

  // Map API VolumePoint {bucket, count, flagged} to chart data shape
  const currentData = data?.series.map((pt) => ({
    label: pt.bucket,
    count: pt.count,
    volume: pt.count, // use count as the Y-axis value (no separate amount field in VolumePoint)
    flagged: pt.flagged,
  })) ?? [];

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
        {isLoading ? (
          <Skeleton className="h-[300px] w-full" />
        ) : isError ? (
          <div className="h-[300px] flex items-center justify-center">
            <p className="text-sm text-gray-500">Unable to load volume data.</p>
          </div>
        ) : currentData.length === 0 ? (
          <div className="h-[300px] flex items-center justify-center">
            <p className="text-sm text-gray-500">No data available for this period.</p>
          </div>
        ) : (
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
                  tickFormatter={(value) => value.toLocaleString('id-ID')}
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
                    Number(value).toLocaleString('id-ID'),
                    'Transaction Count'
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
                  dataKey="count"
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
        )}
      </CardContent>
    </Card>
  );
}
