import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { motion } from 'motion/react';
import { Grid3X3, TrendingUp } from 'lucide-react';

// Generate heatmap data for transaction activity by hour and day
const generateHeatmapData = () => {
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const hours = Array.from({ length: 24 }, (_, i) => i);
  const data = [];

  days.forEach((day, dayIndex) => {
    hours.forEach((hour) => {
      // Simulate realistic transaction patterns
      let intensity = 0.2; // Base intensity
      
      // Higher activity during business hours (8-18)
      if (hour >= 8 && hour <= 18) {
        intensity += 0.4;
      }
      
      // Peak hours (10-12, 14-16)
      if ((hour >= 10 && hour <= 12) || (hour >= 14 && hour <= 16)) {
        intensity += 0.3;
      }
      
      // Weekend patterns (lower activity)
      if (dayIndex >= 5) {
        intensity *= 0.6;
      }
      
      // Friday evening peak
      if (dayIndex === 4 && hour >= 17 && hour <= 20) {
        intensity += 0.2;
      }
      
      // Add some randomness
      intensity += (Math.random() - 0.5) * 0.3;
      intensity = Math.max(0.1, Math.min(1, intensity));
      
      data.push({
        day,
        hour,
        dayIndex,
        intensity,
        transactions: Math.floor(intensity * 1000 + Math.random() * 200),
        fraudScore: Math.random() * 0.1 + (intensity > 0.8 ? 0.05 : 0) // Higher fraud potential during peak times
      });
    });
  });
  
  return data;
};

const heatmapData = generateHeatmapData();

const getIntensityColor = (intensity: number, fraudScore: number) => {
  // Higher fraud score adds red tint
  if (fraudScore > 0.08) {
    return `rgba(220, 38, 127, ${intensity * 0.8 + 0.2})`;
  }
  
  // Normal activity - use new brand color gradient based on intensity
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
  const maxTransactions = Math.max(...heatmapData.map(d => d.transactions));
  const avgFraudScore = heatmapData.reduce((sum, d) => sum + d.fraudScore, 0) / heatmapData.length;
  
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
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-sm bg-pink-600"></div>
                <span>High Risk</span>
              </div>
            </div>
          </div>

          {/* Heatmap Grid */}
          <div className="space-y-1">
            {/* Hour labels */}
            <div className="grid grid-cols-25 gap-0.5 mb-2">
              <div className="w-8"></div> {/* Empty space for day labels */}
              {Array.from({ length: 24 }, (_, i) => i).map((hour) => (
                <div key={hour} className="text-[9px] text-gray-500 text-center w-3">
                  {hour % 6 === 0 ? hour : ''}
                </div>
              ))}
            </div>

            {/* Heatmap rows */}
            {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((day, dayIndex) => (
              <motion.div
                key={day}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.5, delay: dayIndex * 0.1 }}
                className="grid grid-cols-25 gap-0.5 items-center"
              >
                <div className="text-xs text-gray-600 w-8">{day}</div>
                {Array.from({ length: 24 }, (_, hour) => {
                  const dataPoint = heatmapData.find(
                    d => d.day === day && d.hour === hour
                  );
                  return (
                    <div
                      key={hour}
                      className="w-3 h-3 rounded-sm cursor-pointer transition-all duration-200 hover:scale-125 hover:z-10 relative group"
                      style={{
                        backgroundColor: getIntensityColor(dataPoint?.intensity || 0, dataPoint?.fraudScore || 0)
                      }}
                      title={`${day} ${formatHour(hour)}: ${dataPoint?.transactions || 0} transactions${dataPoint?.fraudScore && dataPoint.fraudScore > 0.08 ? ' (High Risk)' : ''}`}
                    >
                      {/* Tooltip on hover */}
                      <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-2 py-1 bg-gray-900 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap z-50">
                        {day} {formatHour(hour)}
                        <br />
                        {dataPoint?.transactions || 0} transactions
                        {dataPoint?.fraudScore && dataPoint.fraudScore > 0.08 && (
                          <><br /><span className="text-red-300">High Risk</span></>
                        )}
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
                {maxTransactions.toLocaleString()}
              </p>
            </motion.div>
            
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.9 }}
              className="text-center"
            >
              <div className="flex items-center justify-center gap-1 mb-1">
                <div className="w-3 h-3 rounded-full bg-gradient-to-r from-pink-500 to-red-500"></div>
                <span className="text-xs text-gray-500">Avg Risk</span>
              </div>
              <p className="text-sm font-semibold text-gray-900">
                {(avgFraudScore * 100).toFixed(1)}%
              </p>
            </motion.div>
          </div>
        </motion.div>
      </CardContent>
    </Card>
  );
}