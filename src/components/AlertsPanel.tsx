import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { ScrollArea } from './ui/scroll-area';
import { AlertTriangle, Shield, Clock, Bell, Check } from 'lucide-react';
import { Skeleton } from './ui/skeleton';
import { useAlerts, useAckAlert } from '../api/queries';
import { formatTime } from '../lib/formatTime';
import type { AlertItem } from '../api/types';

function getAlertColor(severity: string) {
  switch (severity) {
    case 'critical': return 'bg-red-100 text-red-800 border-red-200';
    case 'high':
    case 'warning': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
    case 'info': return 'border-blue-200';
    default: return 'bg-gray-100 text-gray-800 border-gray-200';
  }
}

function getAlertStyle(severity: string): React.CSSProperties | undefined {
  if (severity === 'info') return { backgroundColor: 'rgba(19, 158, 246, 0.1)' };
  return undefined;
}

function getIcon(severity: string) {
  switch (severity) {
    case 'critical': return <AlertTriangle className="w-4 h-4 text-red-600" />;
    case 'high':
    case 'warning': return <Shield className="w-4 h-4 text-yellow-600" />;
    case 'info': return <Bell className="w-4 h-4" style={{color: '#139EF6'}} />;
    default: return <Bell className="w-4 h-4 text-gray-600" />;
  }
}

function AlertRow({ alert, onAck }: { alert: AlertItem; onAck: (id: number) => void }) {
  return (
    <div
      className={`p-4 rounded-lg border ${getAlertColor(alert.severity)} mb-3`}
      style={getAlertStyle(alert.severity)}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5">
          {getIcon(alert.severity)}
        </div>

        <div className="flex-1">
          <div className="flex items-center justify-between mb-1">
            <h4 className="text-sm font-medium">
              {alert.typology ? `${alert.typology} Alert` : `Alert #${alert.id}`}
            </h4>
            <Badge variant="outline" className="text-xs">
              {alert.severity}
            </Badge>
          </div>

          <p className="text-xs text-gray-600 mb-2">
            Event seq: {alert.event_seq}
            {alert.typology ? ` — Typology: ${alert.typology}` : ''}
          </p>

          <div className="flex items-center justify-between text-xs text-gray-500">
            <div className="flex items-center gap-4">
              {!alert.acknowledged && (
                <button
                  className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 transition-colors"
                  onClick={() => onAck(alert.id)}
                >
                  <Check className="w-3 h-3" />
                  Acknowledge
                </button>
              )}
              {alert.acknowledged && (
                <span className="text-green-600 text-xs flex items-center gap-1">
                  <Check className="w-3 h-3" /> Acknowledged
                </span>
              )}
            </div>

            <div className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatTime(alert.event_time)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function AlertsPanel() {
  const { data, isLoading, isError } = useAlerts('all');
  const ackMutation = useAckAlert();

  const alerts = data?.alerts ?? [];
  const criticalCount = alerts.filter((a) => a.severity === 'critical').length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bell className="w-5 h-5" />
          Recent Alerts
          {criticalCount > 0 && (
            <Badge className="bg-red-500 hover:bg-red-500 text-white">
              {criticalCount}
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-20 w-full" />)}
          </div>
        ) : isError ? (
          <p className="text-sm text-gray-500">Unable to load alerts.</p>
        ) : alerts.length === 0 ? (
          <p className="text-sm text-gray-500">No alerts at this time.</p>
        ) : (
          <ScrollArea className="h-80">
            {alerts.map((alert) => (
              <AlertRow
                key={alert.id}
                alert={alert}
                onAck={(id) => ackMutation.mutate(id)}
              />
            ))}
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
