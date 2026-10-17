import { useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { MetricsOverview } from './components/MetricsOverview';
import { TransactionVolume } from './components/TransactionVolume';
import { TransactionHeatmap } from './components/TransactionHeatmap';
import { TransactionMonitor } from './components/TransactionMonitor';
import { FraudAnalytics } from './components/FraudAnalytics';
import { GeographicMap } from './components/GeographicMap';
import { AlertsPanel } from './components/AlertsPanel';
import { UserRiskProfiling } from './components/UserRiskProfiling';
import { useSystemHealth } from './api/queries';
import { Skeleton } from './components/ui/skeleton';

export function SystemHealthCards() {
  const { data, isLoading } = useSystemHealth();

  if (isLoading) {
    return (
      <div className="grid gap-4">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      <div className="p-4 bg-white rounded-lg border">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">Database</span>
          <span className={`text-sm ${data?.db_ok ? 'text-green-600' : 'text-red-600'}`}>
            {data?.db_ok ? 'Online' : 'Offline'}
          </span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
          <div
            className={`h-2 rounded-full ${data?.db_ok ? 'bg-green-500' : 'bg-red-500'}`}
            style={{ width: data?.db_ok ? '100%' : '10%' }}
          ></div>
        </div>
        <p className="text-xs text-gray-500 mt-1">
          {data?.db_ok ? 'Database connection healthy' : 'Database unreachable'}
        </p>
      </div>

      <div className="p-4 bg-white rounded-lg border">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">Model Accuracy</span>
          {data?.model_name ? (
            <span className="text-sm text-green-600">Model: {data.model_name}</span>
          ) : data?.model_accuracy_simulated ? (
            <span className="text-sm text-yellow-600">Simulated (Phase 1)</span>
          ) : (
            <span className="text-sm text-gray-500">—</span>
          )}
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
          <div
            className={`h-2 rounded-full ${data?.model_name ? 'bg-green-500' : 'bg-yellow-400'}`}
            style={{ width: data?.model_name ? '100%' : data?.model_accuracy_simulated ? '60%' : '0%' }}
          ></div>
        </div>
        <p className="text-xs text-gray-500 mt-1">
          {data?.model_name
            ? 'Model scoring active'
            : data?.model_accuracy_simulated
            ? 'Label-replay simulation active — accuracy not yet measured'
            : 'No model accuracy data'}
        </p>
      </div>

      <div className="p-4 bg-white rounded-lg border">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">Cache (Redis)</span>
          <span className={`text-sm ${data?.redis_ok ? 'text-green-600' : 'text-red-600'}`}>
            {data?.redis_ok ? 'Online' : 'Offline'}
          </span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
          <div
            className={`h-2 rounded-full ${data?.redis_ok ? 'bg-green-500' : 'bg-red-500'}`}
            style={{ width: data?.redis_ok ? '100%' : '10%' }}
          ></div>
        </div>
        <p className="text-xs text-gray-500 mt-1">
          {data?.redis_ok ? 'Redis cache operational' : 'Redis unavailable'}
        </p>
      </div>

      <div className="p-4 bg-white rounded-lg border">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">Events Surfaced</span>
          <span className="text-sm" style={{color: '#139EF6'}}>
            {data?.events_surfaced != null ? data.events_surfaced.toLocaleString('id-ID') : '—'}
          </span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
          <div className="h-2 rounded-full" style={{ width: '65%', backgroundColor: '#139EF6' }}></div>
        </div>
        <p className="text-xs text-gray-500 mt-1">Total events processed by system</p>
      </div>
    </div>
  );
}

export default function App() {
  const [currentView, setCurrentView] = useState('/dashboard');

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Fixed Sidebar */}
      <Sidebar currentView={currentView} onNavigate={setCurrentView} />

      {/* Fixed Header */}
      <Header />

      {/* Main Content with proper margins for fixed elements */}
      <main className="ml-64 mt-20 p-6 space-y-6 min-h-screen">
        {/* Conditional Rendering based on current view */}
        {currentView === '/dashboard' ? (
          <>
          {/* Key Metrics Overview */}
          <section>
            <MetricsOverview />
          </section>

          {/* Transaction Volume & Heatmap Section */}
          <section>
            <div className="mb-4">
              <h2 className="text-xl font-semibold text-gray-900">Transaction Monitoring</h2>
              <p className="text-sm text-gray-500 mt-1">Real-time transaction volume analysis and activity patterns</p>
            </div>
            <div className="grid grid-cols-5 gap-6">
              <div className="col-span-3">
                <TransactionVolume />
              </div>
              <div className="col-span-2">
                <TransactionHeatmap />
              </div>
            </div>
          </section>

          {/* Live Transaction Monitor Section */}
          <section>
            <TransactionMonitor />
          </section>

          {/* Analytics Section */}
          <section>
            <div className="mb-4">
              <h2 className="text-xl font-semibold text-gray-900">Fraud Analytics & Insights</h2>
              <p className="text-sm text-gray-500 mt-1">Comprehensive analysis of fraud patterns and detection performance</p>
            </div>
            <FraudAnalytics />
          </section>

          {/* Geographic Analysis */}
          <section className="grid gap-6 lg:grid-cols-2">
            <div>
              <div className="mb-4">
                <h2 className="text-xl font-semibold text-gray-900">Regional Analysis</h2>
                <p className="text-sm text-gray-500 mt-1">Fraud distribution across Indonesian provinces</p>
              </div>
              <GeographicMap />
            </div>

            {/* System Health Section */}
            <div className="space-y-4">
              <div className="mb-4">
                <h2 className="text-xl font-semibold text-gray-900">System Health</h2>
                <p className="text-sm text-gray-500 mt-1">Real-time system performance monitoring</p>
              </div>

              {/* System Status Cards */}
              <SystemHealthCards />
            </div>
          </section>

          {/* Alerts Section */}
          <section>
            <div className="mb-4">
              <h2 className="text-xl font-semibold text-gray-900">Recent Alerts</h2>
              <p className="text-sm text-gray-500 mt-1">Active fraud and system alerts</p>
            </div>
            <AlertsPanel />
          </section>
        </>
        ) : currentView === '/user-risk-profiling' ? (
          /* User Risk Profiling View */
          <UserRiskProfiling />
        ) : (
          /* Placeholder for other views */
          <div className="flex items-center justify-center h-96">
            <div className="text-center">
              <h2 className="text-xl font-semibold text-gray-900">Halaman Sedang Dibangun</h2>
              <p className="text-sm text-gray-500 mt-2">Fitur ini akan segera tersedia</p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
