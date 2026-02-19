import { VERSION_DISPLAY, VERSION_TOOLTIP, VERSION_HISTORY } from "@/lib/version";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { User, LogOut, Settings, Clock, MessageSquare, Bug, Ticket, ClipboardList, LayoutDashboard, BarChart3, Shield } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { TicketSubmissionForm } from "@/components/TicketSubmissionForm";
import { MyTickets } from "@/components/MyTickets";
import { FeedbackSurvey } from "@/components/FeedbackSurvey";

interface NavbarProps {
  onNavigateToProfile: () => void;
  onNavigateToHome: () => void;
  onNavigateToApprovals?: () => void;
  onNavigateToTickets?: () => void;
  onNavigateToFeedback?: () => void;
  onNavigateToDashboard?: () => void;
  onNavigateToAnalytics?: () => void;
  onNavigateToAdminSettings?: () => void;
  onSignOut: () => void;
  isSupervisor?: boolean;
  isAdmin?: boolean;
}

export const Navbar = ({
  onNavigateToProfile,
  onNavigateToHome,
  onNavigateToApprovals,
  onNavigateToTickets,
  onNavigateToFeedback,
  onNavigateToDashboard,
  onNavigateToAnalytics,
  onNavigateToAdminSettings,
  onSignOut,
  isSupervisor = false,
  isAdmin = false,
}: NavbarProps) => {
  const { user, logout } = useAuth();
  const { toast } = useToast();

  const handleSignOut = async () => {
    try {
      await logout();
      toast({
        title: "Signed out",
        description: "You have been signed out successfully.",
      });
      onSignOut();
    } catch (error: any) {
      toast({
        title: "Sign out failed",
        description: error.message,
        variant: "destructive",
      });
    }
  };

  return (
    <nav className="border-b border-border bg-card">
      <div className="container mx-auto px-4 py-4 flex items-center justify-between">
        <button
          onClick={onNavigateToHome}
          className="text-2xl font-bold text-primary hover:opacity-80 transition-opacity flex items-center gap-2"
        >
          Digestor
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="text-xs font-normal text-muted-foreground cursor-help">{VERSION_DISPLAY}</span>
              </TooltipTrigger>
              <TooltipContent side="bottom" align="start" className={isAdmin ? "max-w-xs z-50" : "z-50"}>
                {isAdmin ? (
                  <div className="space-y-1">
                    <p className="font-semibold text-xs mb-2">Version History</p>
                    {VERSION_HISTORY.map((entry, index) => (
                      <p key={index} className="text-xs">
                        <span className="font-medium">v{entry.version}</span> - {entry.timestamp}
                      </p>
                    ))}
                  </div>
                ) : (
                  <p>{VERSION_TOOLTIP}</p>
                )}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </button>

        <div className="flex items-center gap-4">
          {user && onNavigateToDashboard && (
            <Button variant="ghost" onClick={onNavigateToDashboard} className="flex items-center gap-2">
              <LayoutDashboard className="h-5 w-5" />
              <span className="hidden sm:inline">Projects Dashboard</span>
            </Button>
          )}

          {isAdmin && onNavigateToTickets && (
            <Button variant="ghost" onClick={onNavigateToTickets} className="flex items-center gap-2">
              <Ticket className="h-5 w-5" />
              <span className="hidden sm:inline">Tickets Dashboard</span>
            </Button>
          )}

          {isAdmin && onNavigateToFeedback && (
            <Button variant="ghost" onClick={onNavigateToFeedback} className="flex items-center gap-2">
              <ClipboardList className="h-5 w-5" />
              <span className="hidden sm:inline">Feedback Dashboard</span>
            </Button>
          )}

          {isAdmin && onNavigateToAnalytics && (
            <Button variant="ghost" onClick={onNavigateToAnalytics} className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5" />
              <span className="hidden sm:inline">Edit Analytics</span>
            </Button>
          )}

          {user ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="flex items-center gap-2">
                  <User className="h-5 w-5" />
                  <span className="hidden sm:inline">
                    {user.full_name || user.email}
                  </span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <div className="px-2 py-2">
                  <p className="text-sm font-medium">{user.full_name || "User"}</p>
                  <p className="text-xs text-muted-foreground">{user.email}</p>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onNavigateToProfile}>
                  <Settings className="mr-2 h-4 w-4" />
                  Profile Settings
                </DropdownMenuItem>
                {isAdmin && onNavigateToAdminSettings && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={onNavigateToAdminSettings}>
                      <Shield className="mr-2 h-4 w-4" />
                      Admin Settings
                    </DropdownMenuItem>
                  </>
                )}
                <TicketSubmissionForm
                  trigger={
                    <DropdownMenuItem onSelect={(e) => e.preventDefault()}>
                      <Bug className="mr-2 h-4 w-4" />
                      Submit a Ticket
                    </DropdownMenuItem>
                  }
                />
                <MyTickets
                  trigger={
                    <DropdownMenuItem onSelect={(e) => e.preventDefault()}>
                      <ClipboardList className="mr-2 h-4 w-4" />
                      My Tickets
                    </DropdownMenuItem>
                  }
                />
                <FeedbackSurvey
                  trigger={
                    <DropdownMenuItem onSelect={(e) => e.preventDefault()}>
                      <MessageSquare className="mr-2 h-4 w-4" />
                      Feedback Survey
                    </DropdownMenuItem>
                  }
                />
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleSignOut}>
                  <LogOut className="mr-2 h-4 w-4" />
                  Sign Out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <Button variant="default" onClick={onNavigateToHome}>
              Sign In
            </Button>
          )}
        </div>
      </div>
    </nav>
  );
};
