import { useState, useMemo } from 'react';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { ScrollArea } from './ui/scroll-area';
import { Skeleton } from './ui/skeleton';
import {
  Building2,
  User as UserIcon,
  Search,
  Filter,
  Eye,
  AlertTriangle
} from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from './ui/table';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { UserProfileDetailsModal } from './UserProfileDetailsModal';
import { useUserRisk } from '../api/queries';
import type { RiskProfile } from '../api/types';

function getRiskLevelColor(level: string | null) {
  switch (level) {
    case 'High': return 'bg-red-100 text-red-800 border-red-200';
    case 'Medium': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
    case 'Low': return 'bg-green-100 text-green-800 border-green-200';
    default: return 'bg-gray-100 text-gray-800 border-gray-200';
  }
}

function getRiskScoreTextColor(score: number) {
  if (score > 70) return 'text-red-600';
  if (score > 40) return 'text-amber-600';
  return 'text-green-600';
}

function getRiskScoreBarColor(score: number) {
  if (score > 70) return 'bg-red-500';
  if (score > 40) return 'bg-amber-500';
  return 'bg-green-500';
}

export function UserRiskProfiling() {
  const [searchTerm, setSearchTerm] = useState('');
  const [filterRisk, setFilterRisk] = useState('all');
  const [filterType] = useState('all');
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Pass filterRisk to the hook (API supports ?risk=High/Medium/Low)
  const { data, isLoading, isError } = useUserRisk(filterRisk === 'all' ? undefined : filterRisk);
  const profiles: RiskProfile[] = data?.profiles ?? [];

  const filteredProfiles = useMemo(() => {
    return profiles.filter(profile => {
      const matchesSearch = !searchTerm ||
        profile.entity_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        profile.name.toLowerCase().includes(searchTerm.toLowerCase());
      return matchesSearch;
    });
  }, [profiles, searchTerm]);

  // Derive risk distribution from real data
  const riskDistributionData = useMemo(() => {
    const counts = { Low: 0, Medium: 0, High: 0 };
    profiles.forEach(p => {
      const level = p.risk_level as keyof typeof counts;
      if (level in counts) counts[level]++;
    });
    return [
      { name: 'Low', value: counts.Low, color: '#10B981' },
      { name: 'Medium', value: counts.Medium, color: '#F59E0B' },
      { name: 'High', value: counts.High, color: '#EF4444' },
    ].filter(d => d.value > 0);
  }, [profiles]);

  const handleViewProfile = (entityId: string) => {
    setSelectedEntityId(entityId);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedEntityId(null);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">User Risk Profiling</h1>
        <p className="text-sm text-gray-500 mt-1">
          Comprehensive analysis of user and entity risk profiles
        </p>
      </div>

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Risk Distribution Pie Chart */}
        <Card className="p-4">
          <h3 className="font-semibold text-gray-900 mb-1">Risk Level Distribution</h3>
          {isLoading ? (
            <Skeleton className="h-40 w-full mt-2" />
          ) : riskDistributionData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie
                    data={riskDistributionData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                  >
                    {riskDistributionData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
              <div className="mt-1 space-y-2">
                {riskDistributionData.map((item, index) => (
                  <div key={index} className="flex items-center gap-2 text-sm">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.color }}></div>
                    <span className="flex-1">{item.name}</span>
                    <span>{item.value}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-400 mt-4 text-center">No data available</p>
          )}
        </Card>

        {/* Risk Breakdown Bar Chart (derived from current profiles) */}
        <Card className="p-4 lg:col-span-2">
          <h3 className="font-semibold text-gray-900 mb-3">Risk Level Breakdown (Current Filter)</h3>
          {isLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : riskDistributionData.length > 0 ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={riskDistributionData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                  <XAxis dataKey="name" stroke="#6B7280" style={{ fontSize: '12px' }} />
                  <YAxis stroke="#6B7280" style={{ fontSize: '12px' }} />
                  <Tooltip />
                  <Bar dataKey="value" name="Profiles">
                    {riskDistributionData.map((entry, index) => (
                      <Cell key={`bar-cell-${index}`} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="h-64 flex items-center justify-center text-sm text-gray-400">
              No data available for current filter
            </div>
          )}
        </Card>
      </div>

      {/* Filters and Search */}
      <Card className="p-6">
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              placeholder="Search by name or Entity ID..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
          <Select value={filterRisk} onValueChange={setFilterRisk}>
            <SelectTrigger className="w-full md:w-48">
              <SelectValue placeholder="Risk Level" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Risk Levels</SelectItem>
              <SelectItem value="High">High</SelectItem>
              <SelectItem value="Medium">Medium</SelectItem>
              <SelectItem value="Low">Low</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </Card>

      {/* Profiles Table */}
      <Card>
        <div className="p-6 border-b">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-semibold text-gray-900">Risk Profile List</h3>
              <p className="text-sm text-gray-500 mt-1">
                {isLoading
                  ? 'Loading profiles...'
                  : `Showing ${filteredProfiles.length} of ${profiles.length} profiles`}
              </p>
            </div>
            <Button variant="outline" className="gap-2">
              <Filter className="w-4 h-4" />
              Advanced Filters
            </Button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <ScrollArea className="h-[500px]">
            <Table>
              <TableHeader className="sticky top-0 bg-white border-b">
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-6">Entity ID / Name</TableHead>
                  <TableHead>Province</TableHead>
                  <TableHead>Risk Score</TableHead>
                  <TableHead>Risk Status</TableHead>
                  <TableHead>
                    <div>Total</div>
                    <div>Transactions</div>
                  </TableHead>
                  <TableHead>
                    <div>Flagged</div>
                    <div>Transactions</div>
                  </TableHead>
                  <TableHead className="pr-6">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading && Array.from({ length: 6 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell className="pl-6"><Skeleton className="h-4 w-32" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-12" /></TableCell>
                    <TableCell className="pr-6"><Skeleton className="h-8 w-16" /></TableCell>
                  </TableRow>
                ))}

                {isError && (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-8 text-red-500">
                      <AlertTriangle className="w-6 h-6 mx-auto mb-2" />
                      Gagal memuat data profil. Silakan refresh halaman.
                    </TableCell>
                  </TableRow>
                )}

                {!isLoading && !isError && filteredProfiles.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-8 text-gray-400">
                      Tidak ada profil yang sesuai dengan filter.
                    </TableCell>
                  </TableRow>
                )}

                {filteredProfiles.map((profile) => (
                  <TableRow key={profile.entity_id} className="hover:bg-gray-50/50">
                    <TableCell className="pl-6">
                      <div className="flex flex-col gap-1">
                        <code className="text-xs bg-gray-100 px-2 py-0.5 rounded font-mono text-gray-600">
                          {profile.entity_id}
                        </code>
                        <span className="text-sm font-medium text-gray-900">{profile.name}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-gray-700">{profile.province ?? '—'}</span>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-3 min-w-[120px]">
                        <span className={`text-sm font-medium ${getRiskScoreTextColor(profile.risk_score)} min-w-[35px]`}>
                          {Math.round(profile.risk_score)}%
                        </span>
                        <div className="flex-1 bg-gray-200 rounded-full h-2 overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-300 ${getRiskScoreBarColor(profile.risk_score)}`}
                            style={{ width: `${Math.max(Math.min(profile.risk_score, 100), 5)}%` }}
                          />
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        className={`text-xs capitalize ${getRiskLevelColor(profile.risk_level)}`}
                      >
                        {profile.risk_level ?? 'Unknown'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {profile.total_transactions.toLocaleString('en-US')}
                    </TableCell>
                    <TableCell>
                      <span className={profile.flagged_transactions > 0 ? 'text-red-600 font-medium' : ''}>
                        {profile.flagged_transactions}
                      </span>
                    </TableCell>
                    <TableCell className="pr-6">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-8 px-3 text-xs"
                        onClick={() => handleViewProfile(profile.entity_id)}
                      >
                        <Eye className="w-3 h-3 mr-1" />
                        View
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        </div>
      </Card>

      {/* User Profile Details Modal */}
      <UserProfileDetailsModal
        entityId={selectedEntityId}
        isOpen={isModalOpen}
        onClose={handleCloseModal}
      />
    </div>
  );
}
