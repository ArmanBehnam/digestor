import { useState, useEffect, useRef } from "react";
import apiClient from "@/lib/apiClient";
import { useAuth } from "@/hooks/useAuth";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  Bug,
  Lightbulb,
  Sparkles,
  HelpCircle,
  Clock,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Search,
  ArrowLeft,
  Send,
  AlertCircle,
  Image,
  FolderOpen
} from "lucide-react";
import { format } from "date-fns";
import { Navbar } from "@/components/Navbar";

interface TicketData {
  id: string;
  title: string;
  description: string;
  type: string;
  status: string;
  priority: string;
  submitted_by_user_id: string | null;
  submitted_by_email: string;
  submitted_by_name: string | null;
  developer_notes: string | null;
  assigned_to: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  screenshot_url: string | null;
  project_reference: string | null;
}

interface TicketsDashboardProps {
  onNavigateToProfile: () => void;
  onNavigateToHome: () => void;
  onNavigateToApprovals?: () => void;
  onNavigateToTickets?: () => void;
  onNavigateToFeedback?: () => void;
  onNavigateToAdminSettings?: () => void;
  onSignOut: () => void;
  isSupervisor?: boolean;
  isAdmin?: boolean;
}

export const TicketsDashboard = ({
  onNavigateToProfile,
  onNavigateToHome,
  onNavigateToApprovals,
  onNavigateToTickets,
  onNavigateToFeedback,
  onNavigateToAdminSettings,
  onSignOut,
  isSupervisor = false,
  isAdmin = false,
}: TicketsDashboardProps) => {
  const [hasAccess, setHasAccess] = useState<boolean | null>(null);
  const [tickets, setTickets] = useState<TicketData[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTicket, setSelectedTicket] = useState<TicketData | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [priorityFilter, setPriorityFilter] = useState<string>("all");
  const [isUpdating, setIsUpdating] = useState(false);
  const [developerNotes, setDeveloperNotes] = useState("");
  const [newStatus, setNewStatus] = useState<string>("");
  const { toast } = useToast();
  const { user } = useAuth();
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadTickets = async () => {
    setLoading(true);
    try {
      const data = await apiClient.listTickets();
      setTickets((data || []) as TicketData[]);
    } catch (error: any) {
      console.error("Error loading tickets:", error);
      toast({
        title: "Failed to load tickets",
        description: error.message,
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  // Check access on mount
  useEffect(() => {
    setHasAccess(isAdmin || isSupervisor);
  }, [isAdmin, isSupervisor]);

  useEffect(() => {
    if (hasAccess) {
      loadTickets();

      // Set up polling every 30 seconds (replaces realtime subscription)
      pollingRef.current = setInterval(() => {
        loadTickets();
      }, 30000);

      return () => {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
        }
      };
    }
  }, [hasAccess]);

  useEffect(() => {
    if (selectedTicket) {
      setDeveloperNotes(selectedTicket.developer_notes || "");
      setNewStatus(selectedTicket.status);
    }
  }, [selectedTicket]);

  const getTypeIcon = (type: string) => {
    switch (type) {
      case "bug":
        return <Bug className="h-4 w-4 text-destructive" />;
      case "feature_request":
        return <Lightbulb className="h-4 w-4 text-amber-500" />;
      case "feature_removal":
        return <Sparkles className="h-4 w-4 text-primary" />;
      default:
        return <HelpCircle className="h-4 w-4 text-primary" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "submitted":
        return (
          <Badge variant="secondary" className="gap-1">
            <Clock className="h-3 w-3" />
            Submitted
          </Badge>
        );
      case "in_progress":
        return (
          <Badge className="gap-1 bg-amber-500/20 text-amber-600 hover:bg-amber-500/30">
            <Loader2 className="h-3 w-3" />
            In Progress
          </Badge>
        );
      case "resolved":
        return (
          <Badge className="gap-1 bg-accent/20 text-accent hover:bg-accent/30">
            <CheckCircle2 className="h-3 w-3" />
            Resolved
          </Badge>
        );
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  const getPriorityBadge = (priority: string) => {
    switch (priority) {
      case "high":
        return <Badge variant="destructive">High</Badge>;
      case "medium":
        return <Badge className="bg-amber-500/20 text-amber-600 hover:bg-amber-500/30">Medium</Badge>;
      case "low":
        return <Badge className="bg-accent/20 text-accent hover:bg-accent/30">Low</Badge>;
      default:
        return <Badge variant="outline">{priority}</Badge>;
    }
  };

  const getTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      bug: "Bug Report",
      feature_request: "Feature Request",
      feature_removal: "Feature Improvement",
      other: "Other",
    };
    return labels[type] || type;
  };

  const filteredTickets = tickets.filter((ticket) => {
    const matchesSearch =
      ticket.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ticket.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ticket.submitted_by_email.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === "all" || ticket.status === statusFilter;
    const matchesType = typeFilter === "all" || ticket.type === typeFilter;
    const matchesPriority = priorityFilter === "all" || ticket.priority === priorityFilter;
    return matchesSearch && matchesStatus && matchesType && matchesPriority;
  });

  const handleUpdateTicket = async () => {
    if (!selectedTicket) return;

    setIsUpdating(true);
    try {
      const oldStatus = selectedTicket.status;

      // Build update data
      const updateData: Record<string, any> = {
        developer_notes: developerNotes || null,
        status: newStatus,
      };

      if (newStatus === "resolved" && oldStatus !== "resolved") {
        updateData.resolved_at = new Date().toISOString();
      }

      // Backend handles status history, notifications, and audit logging
      await apiClient.updateTicket(selectedTicket.id, updateData);

      toast({
        title: "Ticket Updated",
        description: "The ticket has been updated successfully.",
      });

      setSelectedTicket(null);
      loadTickets();
    } catch (error: any) {
      console.error("Error updating ticket:", error);
      toast({
        title: "Update Failed",
        description: error.message || "Failed to update ticket.",
        variant: "destructive",
      });
    } finally {
      setIsUpdating(false);
    }
  };

  const stats = {
    total: tickets.length,
    submitted: tickets.filter((t) => t.status === "submitted").length,
    inProgress: tickets.filter((t) => t.status === "in_progress").length,
    resolved: tickets.filter((t) => t.status === "resolved").length,
  };

  // Show access denied if user doesn't have permission
  if (hasAccess === false) {
    return (
      <div className="min-h-screen bg-background">
        <Navbar
          onNavigateToProfile={onNavigateToProfile}
          onNavigateToHome={onNavigateToHome}
          onNavigateToApprovals={onNavigateToApprovals}
          onSignOut={onSignOut}
          isSupervisor={isSupervisor}
          isAdmin={isAdmin}
        />
        <div className="container mx-auto px-4 py-8">
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <AlertCircle className="h-16 w-16 text-muted-foreground mb-4" />
            <h1 className="text-2xl font-bold mb-2">Access Denied</h1>
            <p className="text-muted-foreground mb-6">
              You don't have permission to access the Tickets Dashboard.
              <br />
              Only administrators and supervisors can view all tickets.
            </p>
            <Button onClick={onNavigateToHome}>
              <ArrowLeft className="h-4 w-4 mr-2" />
              Go Home
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Navbar
        onNavigateToProfile={onNavigateToProfile}
        onNavigateToHome={onNavigateToHome}
        onNavigateToApprovals={onNavigateToApprovals}
        onNavigateToTickets={onNavigateToTickets}
        onNavigateToFeedback={onNavigateToFeedback}
        onNavigateToAdminSettings={onNavigateToAdminSettings}
        onSignOut={onSignOut}
        isSupervisor={isSupervisor}
        isAdmin={isAdmin}
      />

      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center gap-4 mb-6">
          <Button variant="ghost" onClick={onNavigateToHome}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
          <h1 className="text-2xl font-bold">Tickets Dashboard</h1>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-muted-foreground">Total</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{stats.total}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-muted-foreground flex items-center gap-1">
                <Clock className="h-4 w-4" /> Submitted
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold text-muted-foreground">{stats.submitted}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-muted-foreground flex items-center gap-1">
                <AlertCircle className="h-4 w-4 text-amber-500" /> In Progress
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold text-amber-500">{stats.inProgress}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-muted-foreground flex items-center gap-1">
                <CheckCircle2 className="h-4 w-4 text-accent" /> Resolved
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold text-accent">{stats.resolved}</p>
            </CardContent>
          </Card>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-4 mb-6">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search tickets..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[150px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="submitted">Submitted</SelectItem>
              <SelectItem value="in_progress">In Progress</SelectItem>
              <SelectItem value="resolved">Resolved</SelectItem>
            </SelectContent>
          </Select>
          <Select value={typeFilter} onValueChange={setTypeFilter}>
            <SelectTrigger className="w-[150px]">
              <SelectValue placeholder="Type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Types</SelectItem>
              <SelectItem value="bug">Bug</SelectItem>
              <SelectItem value="feature_request">Feature Request</SelectItem>
              <SelectItem value="feature_removal">Feature Improvement</SelectItem>
              <SelectItem value="other">Other</SelectItem>
            </SelectContent>
          </Select>
          <Select value={priorityFilter} onValueChange={setPriorityFilter}>
            <SelectTrigger className="w-[150px]">
              <SelectValue placeholder="Priority" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Priority</SelectItem>
              <SelectItem value="high">High</SelectItem>
              <SelectItem value="medium">Medium</SelectItem>
              <SelectItem value="low">Low</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={loadTickets} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>

        {/* Tickets List */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : filteredTickets.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <Bug className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>No tickets found.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredTickets.map((ticket) => (
              <Card
                key={ticket.id}
                className="cursor-pointer hover:border-primary/50 transition-colors"
                onClick={() => setSelectedTicket(ticket)}
              >
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3 min-w-0 flex-1">
                      {getTypeIcon(ticket.type)}
                      <div className="min-w-0 flex-1">
                        <h3 className="font-medium truncate">{ticket.title}</h3>
                        <p className="text-sm text-muted-foreground truncate mt-1">
                          {ticket.description.substring(0, 100)}...
                        </p>
                        <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground flex-wrap">
                          <span>{ticket.submitted_by_name || ticket.submitted_by_email}</span>
                          <span>•</span>
                          <span>{format(new Date(ticket.created_at), "MMM d, yyyy h:mm a")}</span>
                          {ticket.project_reference && (
                            <>
                              <span>•</span>
                              <span className="flex items-center gap-1">
                                <FolderOpen className="h-3 w-3" />
                                {ticket.project_reference}
                              </span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      {getStatusBadge(ticket.status)}
                      {getPriorityBadge(ticket.priority)}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Ticket Detail Modal */}
        <Dialog open={!!selectedTicket} onOpenChange={(open) => !open && setSelectedTicket(null)}>
          <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
            {selectedTicket && (
              <>
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2">
                    {getTypeIcon(selectedTicket.type)}
                    {selectedTicket.title}
                  </DialogTitle>
                  <DialogDescription>
                    Submitted by {selectedTicket.submitted_by_name || selectedTicket.submitted_by_email}
                  </DialogDescription>
                </DialogHeader>

                <div className="space-y-4">
                  <div className="flex gap-2 flex-wrap">
                    {getStatusBadge(selectedTicket.status)}
                    {getPriorityBadge(selectedTicket.priority)}
                    <Badge variant="outline">{getTypeLabel(selectedTicket.type)}</Badge>
                  </div>

                  <Separator />

                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-2">Description</h4>
                    <p className="text-sm whitespace-pre-wrap bg-muted/50 p-3 rounded-md">
                      {selectedTicket.description}
                    </p>
                  </div>

                  {selectedTicket.project_reference && (
                    <>
                      <Separator />
                      <div>
                        <h4 className="text-sm font-medium text-muted-foreground mb-2 flex items-center gap-2">
                          <FolderOpen className="h-4 w-4" />
                          Project Reference
                        </h4>
                        <p className="text-sm bg-muted/50 p-3 rounded-md">
                          {selectedTicket.project_reference}
                        </p>
                      </div>
                    </>
                  )}

                  {selectedTicket.screenshot_url && (
                    <>
                      <Separator />
                      <div>
                        <h4 className="text-sm font-medium text-muted-foreground mb-2 flex items-center gap-2">
                          <Image className="h-4 w-4" />
                          Screenshot
                        </h4>
                        <a
                          href={selectedTicket.screenshot_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block"
                        >
                          <img
                            src={selectedTicket.screenshot_url}
                            alt="Ticket screenshot"
                            className="max-w-full max-h-[300px] rounded-md border cursor-pointer hover:opacity-90 transition-opacity"
                          />
                        </a>
                        <p className="text-xs text-muted-foreground mt-1">Click to view full size</p>
                      </div>
                    </>
                  )}

                  <Separator />

                  <div className="space-y-3">
                    <Label>Update Status</Label>
                    <Select value={newStatus} onValueChange={setNewStatus}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="submitted">Submitted</SelectItem>
                        <SelectItem value="in_progress">In Progress</SelectItem>
                        <SelectItem value="resolved">Resolved</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-3">
                    <Label>Developer Notes</Label>
                    <Textarea
                      placeholder="Add notes for the user (will be included in status update emails)"
                      value={developerNotes}
                      onChange={(e) => setDeveloperNotes(e.target.value)}
                      rows={4}
                    />
                  </div>

                  <Separator />

                  <div className="text-xs text-muted-foreground space-y-1">
                    <p><strong>Email:</strong> {selectedTicket.submitted_by_email}</p>
                    <p><strong>Created:</strong> {format(new Date(selectedTicket.created_at), "PPp")}</p>
                    <p><strong>Updated:</strong> {format(new Date(selectedTicket.updated_at), "PPp")}</p>
                    {selectedTicket.resolved_at && (
                      <p><strong>Resolved:</strong> {format(new Date(selectedTicket.resolved_at), "PPp")}</p>
                    )}
                    <p className="font-mono">ID: {selectedTicket.id}</p>
                  </div>

                  <div className="flex justify-end gap-3 pt-2">
                    <Button variant="outline" onClick={() => setSelectedTicket(null)} disabled={isUpdating}>
                      Cancel
                    </Button>
                    <Button onClick={handleUpdateTicket} disabled={isUpdating}>
                      {isUpdating ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          Updating...
                        </>
                      ) : (
                        <>
                          <Send className="h-4 w-4 mr-2" />
                          Update Ticket
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              </>
            )}
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
};

export default TicketsDashboard;
