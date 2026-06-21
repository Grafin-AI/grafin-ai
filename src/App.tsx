import { useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { MetricsOverview } from './components/MetricsOverview';
import { TransactionVolume } from './components/TransactionVolume';
import { TransactionHeatmap } from './components/TransactionHeatmap';
import { TransactionMonitor } from './components/TransactionMonitor';
import { FraudAnalytics } from './components/FraudAnalytics';
import { GeographicMap } from './components/GeographicMap';
import { UserRiskProfiling } from './components/UserRiskProfiling';

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
              <div className="grid gap-4">
                <div className="p-4 bg-white rounded-lg border">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">API Response Time</span>
                    <span className="text-sm text-green-600">23ms</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                    <div className="bg-green-500 h-2 rounded-full" style={{ width: '85%' }}></div>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">Excellent performance</p>
                </div>
                
                <div className="p-4 bg-white rounded-lg border">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Model Accuracy</span>
                    <span className="text-sm text-green-600">99.94%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                    <div className="bg-green-500 h-2 rounded-full" style={{ width: '99%' }}></div>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">Model performing optimally</p>
                </div>
                
                <div className="p-4 bg-white rounded-lg border">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">System Uptime</span>
                    <span className="text-sm text-green-600">99.99%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                    <div className="bg-green-500 h-2 rounded-full" style={{ width: '100%' }}></div>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">Exceptional reliability</p>
                </div>

                <div className="p-4 bg-white rounded-lg border">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Active Connections</span>
                    <span className="text-sm" style={{color: '#139EF6'}}>1,247</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                    <div className="h-2 rounded-full" style={{ width: '65%', backgroundColor: '#139EF6' }}></div>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">Banks connected to platform</p>
                </div>
              </div>
            </div>
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