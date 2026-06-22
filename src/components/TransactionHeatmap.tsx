import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { motion } from 'motion/react';
import { Grid3X3, TrendingUp } from 'lucide-react';
import { Skeleton } from './ui/skeleton';
import { useHeatmap } from '../api/queries';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const getIntensityColor = (intensity: number) => {
  const alpha = intensity * 0.7 + 0.1;
  return `rgba(19, 158, 246, ${alpha})`;
};

const formatHour = (hour: number) => {
  if (hour === 0) return '12 AM';
  if (hour === 12) return '12 PM';
  if (hour < 12) return `${hour} AM`;
  return `${hour - 12} PM`;
};

export function TransactionHeatmap() {
  const { data, isLoading, isError } = useHeatmap();

  // cells is a 7x24 array: cells[dayIndex][hour]
  const cells = data?.cells ?? [];

  // Derive max transactions from raw cell values
  const allValues = cells.flat();
  const maxValue = allValues.length > 0 ? Math.max(...allValues) : 1;

  return (
    <Card>
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Grid3X3 className="w-5 h-5 text-garda-dark-blue" />
              Activity Heatmap
              <Badge variant="secondary" className="ml-2">
                Weekly Pattern
              </Badge>
            </CardTitle>
            <p className="text-sm text-gray-500 mt-1">
              Transaction intensity by hour and day
            </p>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[250px] w-full" />
        ) : isError ? (
          <div className="h-[250px] flex items-center justify-center">
            <p className="text-sm text-gray-500">Unable to load heatmap data.</p>
          </div>
        ) : cells.length === 0 ? (
          <div className="h-[250px] flex items-center justify-center">
            <p className="text-sm text-gray-500">No heatmap data available.</p>
          </div>
        ) : (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.6 }}
          >
            {/* Legend */}
            <div className="flex items-center justify-between mb-4 text-xs text-gray-600">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-sm" style={{backgroundColor: 'rgba(19, 158, 246, 0.2)'}}></div>
                  <span>Low Activity</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-sm bg-garda-dark-blue"></div>
                  <span>High Activity</span>
                </div>
              </div>
            </div>

            {/* Heatmap Grid */}
            <div className="space-y-1">
              {/* Hour labels */}
              <div className="grid grid-cols-25 gap-0.5 mb-2">
                <div className="w-8"></div>
                {Array.from({ length: 24 }, (_, i) => i).map((hour) => (
                  <div key={hour} className="text-[9px] text-gray-500 text-center w-3">
                    {hour % 6 === 0 ? hour : ''}
                  </div>
                ))}
              </div>

              {/* Heatmap rows */}
              {DAYS.map((day, dayIndex) => (
                <motion.div
                  key={day}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.5, delay: dayIndex * 0.1 }}
                  className="grid grid-cols-25 gap-0.5 items-center"
                >
                  <div className="text-xs text-gray-600 w-8">{day}</div>
                  {Array.from({ length: 24 }, (_, hour) => {
                    const rawValue = cells[dayIndex]?.[hour] ?? 0;
                    const intensity = maxValue > 0 ? rawValue / maxValue : 0;
                    return (
                      <div
                        key={hour}
                        className="w-3 h-3 rounded-sm cursor-pointer transition-all duration-200 hover:scale-125 hover:z-10 relative group"
                        style={{
                          backgroundColor: getIntensityColor(intensity)
                        }}
                        title={`${day} ${formatHour(hour)}: ${rawValue} transactions`}
                      >
                        {/* Tooltip on hover */}
                        <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-2 py-1 bg-gray-900 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap z-50">
                          {day} {formatHour(hour)}
                          <br />
                          {rawValue} transactions
                        </div>
                      </div>
                    );
                  })}
                </motion.div>
              ))}
            </div>

            {/* Summary Stats */}
            <div className="grid grid-cols-2 gap-3 mt-6 pt-4 border-t border-gray-100">
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.8 }}
                className="text-center"
              >
                <div className="flex items-center justify-center gap-1 mb-1">
                  <TrendingUp className="w-3 h-3 text-garda-dark-blue" />
                  <span className="text-xs text-gray-500">Peak Activity</span>
                </div>
                <p className="text-sm font-semibold text-gray-900">
                  {maxValue.toLocaleString()}
                </p>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.9 }}
                className="text-center"
              >
                <div className="flex items-center justify-center gap-1 mb-1">
                  <div className="w-3 h-3 rounded-full bg-gradient-to-r from-blue-400 to-blue-600"></div>
                  <span className="text-xs text-gray-500">Total Cells</span>
                </div>
                <p className="text-sm font-semibold text-gray-900">
                  {allValues.length}
                </p>
              </motion.div>
            </div>
          </motion.div>
        )}
      </CardContent>
    </Card>
  );
}
