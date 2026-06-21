import { useState } from 'react';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { ScrollArea } from './ui/scroll-area';
import { 
  Users, 
  AlertTriangle, 
  TrendingUp, 
  Building2, 
  User as UserIcon,
  Search,
  Filter,
  Eye,
  ChevronDown,
  Shield,
  Activity
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

interface RiskProfile {
  id: string;
  paymentId: string;
  entityType: 'Individual' | 'Company';
  riskLevel: 'Low' | 'Medium' | 'High';
  riskScore: number;
  totalTransactions: number;
  flaggedTransactions: number;
  lastActivity: string;
  accountAge: string;
}

// Mock data for user risk profiles
const mockProfiles: RiskProfile[] = [
  {
    id: '1',
    paymentId: '••••••••4521',
    entityType: 'Company',
    riskLevel: 'High',
    riskScore: 87,
    totalTransactions: 1247,
    flaggedTransactions: 34,
    lastActivity: '5 min ago',
    accountAge: '2 years'
  },
  {
    id: '2',
    paymentId: '••••••••7834',
    entityType: 'Individual',
    riskLevel: 'High',
    riskScore: 78,
    totalTransactions: 342,
    flaggedTransactions: 12,
    lastActivity: '12 min ago',
    accountAge: '1.5 years'
  },
  {
    id: '3',
    paymentId: '••••••••2190',
    entityType: 'Company',
    riskLevel: 'High',
    riskScore: 81,
    totalTransactions: 892,
    flaggedTransactions: 23,
    lastActivity: '23 min ago',
    accountAge: '3 years'
  },
  {
    id: '4',
    paymentId: '••••••••5612',
    entityType: 'Individual',
    riskLevel: 'Medium',
    riskScore: 54,
    totalTransactions: 156,
    flaggedTransactions: 3,
    lastActivity: '1 hour ago',
    accountAge: '8 months'
  },
  {
    id: '5',
    paymentId: '••••••••9087',
    entityType: 'Company',
    riskLevel: 'Medium',
    riskScore: 48,
    totalTransactions: 567,
    flaggedTransactions: 5,
    lastActivity: '2 hours ago',
    accountAge: '4 years'
  },
  {
    id: '6',
    paymentId: '••••••••3421',
    entityType: 'Individual',
    riskLevel: 'Low',
    riskScore: 23,
    totalTransactions: 89,
    flaggedTransactions: 0,
    lastActivity: '3 hours ago',
    accountAge: '6 months'
  },
  {
    id: '7',
    paymentId: '••••••••8765',
    entityType: 'Company',
    riskLevel: 'Low',
    riskScore: 18,
    totalTransactions: 234,
    flaggedTransactions: 1,
    lastActivity: '4 hours ago',
    accountAge: '2.5 years'
  },
  {
    id: '8',
    paymentId: '••••••••6543',
    entityType: 'Individual',
    riskLevel: 'Medium',
    riskScore: 61,
    totalTransactions: 278,
    flaggedTransactions: 7,
    lastActivity: '5 hours ago',
    accountAge: '1 year'
  },
  {
    id: '9',
    paymentId: '••••••••1928',
    entityType: 'Individual',
    riskLevel: 'High',
    riskScore: 92,
    totalTransactions: 512,
    flaggedTransactions: 45,
    lastActivity: '15 min ago',
    accountAge: '9 months'
  },
  {
    id: '10',
    paymentId: '••••••••3765',
    entityType: 'Company',
    riskLevel: 'Medium',
    riskScore: 58,
    totalTransactions: 743,
    flaggedTransactions: 8,
    lastActivity: '1 hour ago',
    accountAge: '5 years'
  },
  {
    id: '11',
    paymentId: '••••••••4982',
    entityType: 'Individual',
    riskLevel: 'Low',
    riskScore: 15,
    totalTransactions: 67,
    flaggedTransactions: 0,
    lastActivity: '6 hours ago',
    accountAge: '3 months'
  },
  {
    id: '12',
    paymentId: '••••••••7291',
    entityType: 'Company',
    riskLevel: 'High',
    riskScore: 84,
    totalTransactions: 1523,
    flaggedTransactions: 28,
    lastActivity: '30 min ago',
    accountAge: '1.8 years'
  },
  {
    id: '13',
    paymentId: '••••••••5439',
    entityType: 'Individual',
    riskLevel: 'Medium',
    riskScore: 67,
    totalTransactions: 198,
    flaggedTransactions: 11,
    lastActivity: '2 hours ago',
    accountAge: '1.2 years'
  },
  {
    id: '14',
    paymentId: '••••••••8012',
    entityType: 'Company',
    riskLevel: 'Low',
    riskScore: 22,
    totalTransactions: 421,
    flaggedTransactions: 2,
    lastActivity: '7 hours ago',
    accountAge: '6 years'
  },
  {
    id: '15',
    paymentId: '••••••••2647',
    entityType: 'Individual',
    riskLevel: 'High',
    riskScore: 89,
    totalTransactions: 456,
    flaggedTransactions: 38,
    lastActivity: '45 min ago',
    accountAge: '7 months'
  },
  {
    id: '16',
    paymentId: '••••••••9134',
    entityType: 'Company',
    riskLevel: 'Medium',
    riskScore: 52,
    totalTransactions: 834,
    flaggedTransactions: 6,
    lastActivity: '3 hours ago',
    accountAge: '3.5 years'
  },
  {
    id: '17',
    paymentId: '••••••••6728',
    entityType: 'Individual',
    riskLevel: 'Low',
    riskScore: 28,
    totalTransactions: 112,
    flaggedTransactions: 1,
    lastActivity: '4 hours ago',
    accountAge: '1.1 years'
  },
  {
    id: '18',
    paymentId: '••••••••3856',
    entityType: 'Company',
    riskLevel: 'High',
    riskScore: 79,
    totalTransactions: 967,
    flaggedTransactions: 19,
    lastActivity: '1.5 hours ago',
    accountAge: '2.2 years'
  },
  {
    id: '19',
    paymentId: '••••••••5291',
    entityType: 'Individual',
    riskLevel: 'Medium',
    riskScore: 46,
    totalTransactions: 187,
    flaggedTransactions: 4,
    lastActivity: '5 hours ago',
    accountAge: '10 months'
  },
  {
    id: '20',
    paymentId: '••••••••7483',
    entityType: 'Company',
    riskLevel: 'Low',
    riskScore: 19,
    totalTransactions: 298,
    flaggedTransactions: 0,
    lastActivity: '8 hours ago',
    accountAge: '4.5 years'
  },
  {
    id: '21',
    paymentId: '••••••••4126',
    entityType: 'Individual',
    riskLevel: 'High',
    riskScore: 75,
    totalTransactions: 329,
    flaggedTransactions: 16,
    lastActivity: '20 min ago',
    accountAge: '1.3 years'
  },
  {
    id: '22',
    paymentId: '••••••••8957',
    entityType: 'Company',
    riskLevel: 'Medium',
    riskScore: 63,
    totalTransactions: 1089,
    flaggedTransactions: 14,
    lastActivity: '2.5 hours ago',
    accountAge: '2.8 years'
  },
  {
    id: '23',
    paymentId: '••••••••2318',
    entityType: 'Individual',
    riskLevel: 'Low',
    riskScore: 31,
    totalTransactions: 143,
    flaggedTransactions: 1,
    lastActivity: '6 hours ago',
    accountAge: '2 years'
  },
  {
    id: '24',
    paymentId: '••••••••6074',
    entityType: 'Company',
    riskLevel: 'High',
    riskScore: 86,
    totalTransactions: 1324,
    flaggedTransactions: 31,
    lastActivity: '40 min ago',
    accountAge: '1.5 years'
  },
  {
    id: '25',
    paymentId: '••••••••9562',
    entityType: 'Individual',
    riskLevel: 'Medium',
    riskScore: 55,
    totalTransactions: 234,
    flaggedTransactions: 5,
    lastActivity: '3.5 hours ago',
    accountAge: '1.7 years'
  }
];

const riskDistributionData = [
  { name: 'Low', value: 1334, color: '#10B981' },
  { name: 'Medium', value: 876, color: '#F59E0B' },
  { name: 'High', value: 324, color: '#EF4444' }
];

const riskTrendData = [
  { month: 'Apr', high: 298, medium: 756, low: 1167 },
  { month: 'May', high: 312, medium: 823, low: 1254 },
  { month: 'Jun', high: 287, medium: 891, low: 1269 },
  { month: 'Jul', high: 334, medium: 867, low: 1305 },
  { month: 'Aug', high: 324, medium: 876, low: 1334 }
];

function getRiskLevelColor(level: string) {
  switch (level) {
    case 'High':
      return 'bg-red-100 text-red-800 border-red-200';
    case 'Medium':
      return 'bg-yellow-100 text-yellow-800 border-yellow-200';
    case 'Low':
      return 'bg-green-100 text-green-800 border-green-200';
    default:
      return 'bg-gray-100 text-gray-800 border-gray-200';
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
  const [filterType, setFilterType] = useState('all');
  const [selectedProfile, setSelectedProfile] = useState<RiskProfile | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const filteredProfiles = mockProfiles.filter(profile => {
    const matchesSearch = profile.paymentId.includes(searchTerm) ||
                         profile.id.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesRisk = filterRisk === 'all' || profile.riskLevel === filterRisk;
    const matchesType = filterType === 'all' || profile.entityType === filterType;
    return matchesSearch && matchesRisk && matchesType;
  });

  const totalProfiles = 2534;
  const highRiskProfiles = 413;
  const flaggedToday = 23;
  const avgRiskScore = 42.3;

  const handleViewProfile = (profileId: string) => {
    const profile = mockProfiles.find(p => p.id === profileId);
    if (profile) {
      setSelectedProfile(profile);
      setIsModalOpen(true);
    }
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedProfile(null);
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
                <div className="w-3 h-3 rounded-full" style={{backgroundColor: item.color}}></div>
                <span className="flex-1">{item.name}</span>
                <span>{item.value}</span>
              </div>
            ))}
          </div>
        </Card>

        {/* Risk Trend Chart */}
        <Card className="p-4 lg:col-span-2">
          <h3 className="font-semibold text-gray-900 mb-3">Risk Trend - Last 5 Months</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={riskTrendData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                <XAxis dataKey="month" stroke="#6B7280" style={{ fontSize: '12px' }} />
                <YAxis stroke="#6B7280" style={{ fontSize: '12px' }} />
                <Tooltip />
                <Bar dataKey="high" stackId="a" fill="#EF4444" name="High" />
                <Bar dataKey="medium" stackId="a" fill="#F59E0B" name="Medium" />
                <Bar dataKey="low" stackId="a" fill="#10B981" name="Low" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* Filters and Search */}
      <Card className="p-6">
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              placeholder="Search by name or Payment ID..."
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
          <Select value={filterType} onValueChange={setFilterType}>
            <SelectTrigger className="w-full md:w-48">
              <SelectValue placeholder="Entity Type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Types</SelectItem>
              <SelectItem value="Company">Company</SelectItem>
              <SelectItem value="Individual">Individual</SelectItem>
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
                Showing {filteredProfiles.length} of {mockProfiles.length} profiles
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
                  <TableHead className="pl-6">Payment ID</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Account Age</TableHead>
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
                {filteredProfiles.map((profile) => (
                  <TableRow key={profile.id} className="hover:bg-gray-50/50">
                    <TableCell className="pl-6">
                      <code className="text-sm bg-gray-100 px-2 py-1 rounded font-mono">
                        {profile.paymentId}
                      </code>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="gap-1">
                        {profile.entityType === 'Company' ? (
                          <Building2 className="w-3 h-3" />
                        ) : (
                          <UserIcon className="w-3 h-3" />
                        )}
                        {profile.entityType}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-gray-700">{profile.accountAge}</span>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-3 min-w-[120px]">
                        <span className={`text-sm font-medium ${getRiskScoreTextColor(profile.riskScore)} min-w-[35px]`}>
                          {Math.round(profile.riskScore)}%
                        </span>
                        <div className="flex-1 bg-gray-200 rounded-full h-2 overflow-hidden">
                          <div 
                            className={`h-full rounded-full transition-all duration-300 ${getRiskScoreBarColor(profile.riskScore)}`}
                            style={{ width: `${Math.max(profile.riskScore, 5)}%` }}
                          />
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge 
                        className={`text-xs capitalize ${getRiskLevelColor(profile.riskLevel)}`}
                      >
                        {profile.riskLevel}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {profile.totalTransactions.toLocaleString('en-US')}
                    </TableCell>
                    <TableCell>
                      <span className={profile.flaggedTransactions > 0 ? 'text-red-600 font-medium' : ''}>
                        {profile.flaggedTransactions}
                      </span>
                    </TableCell>
                    <TableCell className="pr-6">
                      <Button 
                        variant="outline" 
                        size="sm"
                        className="h-8 px-3 text-xs"
                        onClick={() => handleViewProfile(profile.id)}
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
        profile={selectedProfile}
        isOpen={isModalOpen}
        onClose={handleCloseModal}
      />
    </div>
  );
}
