import { Bell, Settings, User, Search, Menu, Play, Pause, Clock } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Badge } from './ui/badge';
import { Skeleton } from './ui/skeleton';
import { useSimState, useSimControl } from '../api/queries';
import { useAuth } from '../auth/AuthContext';

interface HeaderProps {
  onMenuClick?: () => void;
}

const SPEED_OPTIONS = [1, 2, 5, 10, 20] as const;

export function Header({ onMenuClick }: HeaderProps) {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const { data: simState, isLoading: simLoading } = useSimState();
  const simControl = useSimControl();

  const handleToggleRunning = () => {
    if (!simState) return;
    simControl.mutate({ running: !simState.running });
  };

  const handleSpeedChange = (speed: number) => {
    simControl.mutate({ speed });
  };

  const formatSimNow = (simNow: string) => {
    try {
      return new Date(simNow).toLocaleString('id-ID', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return simNow;
    }
  };

  return (
    <header className="fixed top-0 left-64 right-0 bg-white border-b border-gray-200 px-6 py-4 z-40">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          {/* Mobile menu button */}
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={onMenuClick}
          >
            <Menu className="w-5 h-5" />
          </Button>

          <div>
            <h1 className="text-lg font-semibold text-gray-900">Fraud Detection Dashboard</h1>
            <p className="text-sm text-gray-500">Real-time monitoring and analytics</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Sim Clock Indicator */}
          <div className="flex items-center gap-2 border border-gray-200 rounded-lg px-3 py-1.5 bg-gray-50">
            {simLoading ? (
              <Skeleton className="h-4 w-40" />
            ) : simState ? (
              <>
                <Clock className="w-4 h-4 text-gray-500 shrink-0" />
                <div className="flex flex-col min-w-0">
                  <span className="text-xs font-medium text-gray-700 leading-tight truncate max-w-[160px]">
                    {formatSimNow(simState.sim_now)}
                  </span>
                  <div className="flex items-center gap-1">
                    <div className={`w-1.5 h-1.5 rounded-full ${simState.running ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`} />
                    <span className="text-xs text-gray-500">
                      {simState.running ? `${simState.speed}x` : 'Paused'}
                    </span>
                  </div>
                </div>

                {/* Admin-only controls */}
                {isAdmin && (
                  <div className="flex items-center gap-1 ml-1 border-l border-gray-300 pl-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0 hover:bg-gray-200"
                      onClick={handleToggleRunning}
                      disabled={simControl.isPending}
                      title={simState.running ? 'Pause simulation' : 'Resume simulation'}
                    >
                      {simState.running ? (
                        <Pause className="w-3 h-3 text-gray-600" />
                      ) : (
                        <Play className="w-3 h-3 text-gray-600" />
                      )}
                    </Button>
                    <select
                      className="text-xs border border-gray-200 rounded px-1 py-0.5 bg-white text-gray-700 cursor-pointer h-6"
                      value={simState.speed}
                      onChange={(e) => handleSpeedChange(Number(e.target.value))}
                      disabled={simControl.isPending}
                      title="Simulation speed"
                    >
                      {SPEED_OPTIONS.map(s => (
                        <option key={s} value={s}>{s}x</option>
                      ))}
                    </select>
                  </div>
                )}
              </>
            ) : (
              <span className="text-xs text-gray-400 flex items-center gap-1">
                <Clock className="w-3 h-3" />
                Sim unavailable
              </span>
            )}
          </div>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
            <Input
              placeholder="Search transactions, banks..."
              className="pl-10 w-72"
            />
          </div>

          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" className="relative">
              <Bell className="w-5 h-5" />
              <Badge className="absolute -top-1 -right-1 h-5 w-5 p-0 text-xs bg-red-500 hover:bg-red-500">
                3
              </Badge>
            </Button>

            <Button variant="ghost" size="icon">
              <Settings className="w-5 h-5" />
            </Button>

            <div className="flex items-center gap-2 pl-2 border-l border-gray-200">
              <div className="text-right">
                <p className="text-sm font-medium text-gray-900">{user?.email ?? 'Admin User'}</p>
                <p className="text-xs text-gray-500">{user?.role ?? 'admin'}@gardaai.com</p>
              </div>
              <Button variant="ghost" size="icon" className="rounded-full">
                <User className="w-5 h-5" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
