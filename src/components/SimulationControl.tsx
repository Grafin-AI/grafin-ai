import { Clock, Pause, Play } from 'lucide-react';
import { Button } from './ui/button';
import { Skeleton } from './ui/skeleton';
import { useSimControl, useSimState, useSystemHealth } from '../api/queries';
import { useAuth } from '../auth/AuthContext';

const SPEED_OPTIONS = [1, 2, 5, 10, 20] as const;

function formatSimNow(simNow: string): string {
  try {
    return new Date(simNow).toLocaleString('id-ID', {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return simNow;
  }
}

export function SimulationControl() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const { data: simState, isLoading } = useSimState();
  const { data: health } = useSystemHealth();
  const simControl = useSimControl();

  const toggleRunning = () => {
    if (simState) simControl.mutate({ running: !simState.running });
  };
  const changeSpeed = (speed: number) => simControl.mutate({ speed });

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">Simulation Control</h2>
        <p className="text-sm text-gray-500 mt-1">
          Replay clock for the demo dataset{isAdmin ? '' : ' (read-only)'}
        </p>
      </div>

      <div className="bg-white rounded-lg border p-6 space-y-6">
        {isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : simState ? (
          <>
            <div className="flex items-center gap-3">
              <Clock className="w-6 h-6 text-gray-400" />
              <div>
                <div className="text-2xl font-semibold text-gray-900" data-testid="sim-now">
                  {formatSimNow(simState.sim_now)}
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      simState.running ? 'bg-green-500 animate-pulse' : 'bg-gray-400'
                    }`}
                  />
                  <span className="text-sm text-gray-600">
                    {simState.running ? `Running · ${simState.speed}x` : 'Paused'}
                  </span>
                </div>
              </div>
            </div>

            {isAdmin && (
              <div className="flex items-center gap-3 border-t pt-4">
                <Button
                  onClick={toggleRunning}
                  disabled={simControl.isPending}
                  variant="outline"
                  className="gap-2"
                >
                  {simState.running ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                  {simState.running ? 'Pause' : 'Resume'}
                </Button>
                <label htmlFor="sim-speed" className="text-sm text-gray-600">Speed</label>
                <select
                  id="sim-speed"
                  aria-label="Simulation speed"
                  className="text-sm border border-gray-200 rounded px-2 py-1 bg-white text-gray-700 cursor-pointer"
                  value={simState.speed}
                  onChange={(e) => changeSpeed(Number(e.target.value))}
                  disabled={simControl.isPending}
                >
                  {SPEED_OPTIONS.map((s) => (
                    <option key={s} value={s}>{s}x</option>
                  ))}
                </select>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4 border-t pt-4">
              <div>
                <p className="text-xs text-gray-500">Events surfaced</p>
                <p className="text-lg font-medium text-gray-900" data-testid="events-surfaced">
                  {health ? health.events_surfaced.toLocaleString('id-ID') : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500">State</p>
                <p className="text-lg font-medium text-gray-900">
                  {simState.running ? 'Running' : 'Paused'}
                </p>
              </div>
            </div>
          </>
        ) : (
          <p className="text-sm text-gray-400">Simulation unavailable</p>
        )}
      </div>
    </div>
  );
}
