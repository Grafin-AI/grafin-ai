import { useState } from 'react';
import gardaLogo from 'figma:asset/db1da7b05c661826c500feb1fd5509a19ea8cfd0.png';
import { 
  BarChart3, 
  Shield, 
  CreditCard, 
  Building, 
  FileText, 
  Bell, 
  Settings, 
  Users, 
  TrendingUp,
  Map,
  Database,
  Activity,
  ChevronDown,
  ChevronRight,
  UserCheck
} from 'lucide-react';
import { Button } from './ui/button';
import { ScrollArea } from './ui/scroll-area';
import { Badge } from './ui/badge';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from './ui/collapsible';
import { useAuth } from '../auth/AuthContext';

interface NavItem {
  title: string;
  icon: React.ReactNode;
  href: string;
  badge?: string;
  children?: NavItem[];
}

interface SidebarProps {
  currentView?: string;
  onNavigate?: (view: string) => void;
}

const navigationItems: NavItem[] = [
  {
    title: "Dashboard",
    icon: <BarChart3 className="w-4 h-4" />,
    href: "/dashboard"
  },
  {
    title: "User Risk Profiling",
    icon: <UserCheck className="w-4 h-4" />,
    href: "/user-risk-profiling"
  },
  {
    title: "Settings",
    icon: <Settings className="w-4 h-4" />,
    href: "/settings"
  }
];

interface NavItemComponentProps {
  item: NavItem;
  isActive?: boolean;
  level?: number;
  onNavigate?: (view: string) => void;
  currentView?: string;
}

function NavItemComponent({ item, isActive = false, level = 0, onNavigate, currentView }: NavItemComponentProps) {
  const [isOpen, setIsOpen] = useState(false);
  const hasChildren = item.children && item.children.length > 0;

  const handleClick = () => {
    if (onNavigate && !hasChildren) {
      onNavigate(item.href);
    }
  };

  if (hasChildren) {
    return (
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CollapsibleTrigger asChild>
          <Button 
            variant="ghost" 
            className={`w-full justify-between h-10 px-3 ${
              isActive ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'
            }`}
            style={{ paddingLeft: `${12 + level * 16}px` }}
          >
            <div className="flex items-center gap-3">
              {item.icon}
              <span className="text-sm">{item.title}</span>
              {item.badge && (
                <Badge variant="secondary" className="ml-auto h-5 px-1.5 text-xs">
                  {item.badge}
                </Badge>
              )}
            </div>
            {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-1">
          {item.children?.map((child, index) => (
            <NavItemComponent 
              key={index} 
              item={child} 
              level={level + 1}
              isActive={currentView === child.href}
              onNavigate={onNavigate}
              currentView={currentView}
            />
          ))}
        </CollapsibleContent>
      </Collapsible>
    );
  }

  return (
    <Button 
      variant="ghost" 
      className={`w-full justify-start h-10 px-3 ${
        isActive ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'
      }`}
      style={{ paddingLeft: `${12 + level * 16}px` }}
      onClick={handleClick}
    >
      <div className="flex items-center gap-3 w-full">
        {item.icon}
        <span className="text-sm">{item.title}</span>
        {item.badge && (
          <Badge variant="secondary" className="ml-auto h-5 px-1.5 text-xs">
            {item.badge}
          </Badge>
        )}
      </div>
    </Button>
  );
}

export function Sidebar({ currentView = '/dashboard', onNavigate }: SidebarProps) {
  const { user } = useAuth();
  const simItem: NavItem = {
    title: 'Simulation',
    icon: <Activity className="w-4 h-4" />,
    href: '/simulation',
  };
  const items: NavItem[] =
    user?.role === 'admin'
      ? [...navigationItems.slice(0, 2), simItem, ...navigationItems.slice(2)]
      : navigationItems;

  return (
    <div className="fixed left-0 top-0 w-64 bg-white border-r border-gray-200 h-screen flex flex-col z-50">
      {/* Logo Header */}
      <div className="p-6 border-b border-gray-200">
        <div className="flex flex-col gap-2 items-start">
          <img 
            src={gardaLogo} 
            alt="GardaAI" 
            className="h-8 w-auto object-contain max-w-full self-start" 
          />
          <p className="text-xs text-gray-500">Fraud & Anomaly Detection Platform</p>
        </div>
      </div>

      {/* Navigation */}
      <ScrollArea className="flex-1 p-4">
        <nav className="space-y-1">
          {items.map((item, index) => (
            <NavItemComponent
              key={index}
              item={item}
              isActive={currentView === item.href}
              onNavigate={onNavigate}
              currentView={currentView}
            />
          ))}
        </nav>
      </ScrollArea>

      {/* Footer */}
      <div className="p-4 border-t border-gray-200">
        <div className="flex items-center gap-3 p-3 rounded-lg" style={{backgroundColor: 'rgba(19, 158, 246, 0.1)'}}>
          <div className="w-8 h-8 bg-primary rounded-full flex items-center justify-center">
            <Shield className="w-4 h-4 text-white" />
          </div>
          <div className="flex-1">
            <p className="text-xs font-medium text-gray-900">System Status</p>
            <p className="text-xs text-green-600">All systems operational</p>
          </div>
        </div>
      </div>
    </div>
  );
}