import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Skeleton } from './ui/skeleton';
import { useFraudAnalytics } from '../api/queries';

export function FraudAnalytics() {
  const { data, isLoading, isError } = useFraudAnalytics();

  // Map API field names to component field names at the boundary
  const topSuspectedFraudData = data?.distribution.map((item) => ({
    fraudType: item.typology,
    totalAmount: item.total_amount,
    count: item.count,
  })) ?? [];

  const detection = data?.detection;

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-3">
        <Card><CardContent className="pt-6"><Skeleton className="h-[300px] w-full" /></CardContent></Card>
        <Card><CardContent className="pt-6"><Skeleton className="h-[300px] w-full" /></CardContent></Card>
        <Card><CardContent className="pt-6"><Skeleton className="h-[300px] w-full" /></CardContent></Card>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="col-span-3">
          <CardContent className="pt-6">
            <p className="text-sm text-gray-500">Unable to load fraud analytics.</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-3">
      {/* Detection Metrics card replacing the static Fraud Score Distribution */}
      <Card>
        <CardHeader>
          <CardTitle>Detection Metrics</CardTitle>
        </CardHeader>
        <CardContent>
          {detection ? (
            <div className="space-y-4 mt-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Precision</span>
                <span className="text-sm font-semibold">{(detection.precision * 100).toFixed(1)}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${detection.precision * 100}%` }}></div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Recall</span>
                <span className="text-sm font-semibold">{(detection.recall * 100).toFixed(1)}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div className="bg-green-500 h-2 rounded-full" style={{ width: `${detection.recall * 100}%` }}></div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">F1 Score</span>
                <span className="text-sm font-semibold">{(detection.f1 * 100).toFixed(1)}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div className="bg-purple-500 h-2 rounded-full" style={{ width: `${detection.f1 * 100}%` }}></div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-500 mt-4">No detection metrics available.</p>
          )}
        </CardContent>
      </Card>

      {/* Fraud count by typology */}
      <Card>
        <CardHeader>
          <CardTitle>Fraud by Typology (Count)</CardTitle>
        </CardHeader>
        <CardContent>
          {topSuspectedFraudData.length === 0 ? (
            <p className="text-sm text-gray-500">No data available.</p>
          ) : (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={topSuspectedFraudData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="fraudType" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="count" fill="var(--garda-dark-blue)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Top Suspected Fraud by Amount */}
      <Card>
        <CardHeader>
          <CardTitle>Top Suspected Fraud</CardTitle>
        </CardHeader>
        <CardContent>
          {topSuspectedFraudData.length === 0 ? (
            <p className="text-sm text-gray-500">No data available.</p>
          ) : (
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
          )}
        </CardContent>
      </Card>
    </div>
  );
}
