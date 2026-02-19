import { useState, useEffect } from "react";
import apiClient from "@/lib/apiClient";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Ticket,
  Bug,
  Lightbulb,
  Sparkles,
  HelpCircle,
  Clock,
  CheckCircle2,
  Loader2,
  RefreshCw,
  MessageSquare,
  Image,
  FolderOpen
} from "lucide-react";
import { format } from "date-fns";

interface TicketData {
  id: string;
  title: string;
  description: string;
  type: string;
  status: string;
  priority: string;
  developer_notes: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  screenshot_url: string | null;
  project_reference: string | null;
}

interface MyTicketsProps {
  trigger?: React.ReactNode;
}

export const MyTickets = ({ trigger }: MyTicketsProps) => {
  const [open, setOpen] = useState(false);
  const [tickets, setTickets] = useState<TicketData[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedTicket, setSelectedTicket] = useState<TicketData | null>(null);
  const { toast } = useToast();

  const loadTickets = async () => {
    setLoading(true);
    try {
      const data = await apiClient.listMyTickets();
      setTickets((data?.tickets || data || []) as TicketData[]);
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

  useEffect(() => {
    if (open) {
      loadTickets();
    }
  }, [open]);

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
            <Loader2 className="h-3 w-3 animate-spin" />
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

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger || (
          <Button variant="ghost" size="sm">
            <Ticket className="h-4 w-4 mr-2" />
            My Tickets
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[700px] max-h-[80vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Ticket className="h-5 w-5" />
            My Tickets
          </DialogTitle>
          <DialogDescription>
            View and track the status of your submitted tickets.
          </DialogDescription>
        </DialogHeader>

        <div className="flex justify-end mb-2">
          <Button variant="ghost" size="sm" onClick={loadTickets} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>

        {selectedTicket ? (
          <div className="space-y-4">
            <Button variant="ghost" size="sm" onClick={() => setSelectedTicket(null)}>
              &larr; Back to list
            </Button>

            <div className="space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-2">
                  {getTypeIcon(selectedTicket.type)}
                  <h3 className="font-semibold text-lg">{selectedTicket.title}</h3>
                </div>
                {getStatusBadge(selectedTicket.status)}
              </div>

              <div className="flex gap-2 flex-wrap">
                <Badge variant="outline">{getTypeLabel(selectedTicket.type)}</Badge>
                {getPriorityBadge(selectedTicket.priority)}
              </div>

              <Separator />

              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-2">Description</h4>
                <p className="text-sm whitespace-pre-wrap">{selectedTicket.description}</p>
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
                        className="max-w-full max-h-[200px] rounded-md border cursor-pointer hover:opacity-90 transition-opacity"
                      />
                    </a>
                    <p className="text-xs text-muted-foreground mt-1">Click to view full size</p>
                  </div>
                </>
              )}

              {selectedTicket.developer_notes && (
                <>
                  <Separator />
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-2 flex items-center gap-2">
                      <MessageSquare className="h-4 w-4" />
                      Developer Notes
                    </h4>
                    <p className="text-sm whitespace-pre-wrap bg-muted/50 p-3 rounded-md">
                      {selectedTicket.developer_notes}
                    </p>
                  </div>
                </>
              )}

              <Separator />

              <div className="text-xs text-muted-foreground space-y-1">
                <p>Created: {format(new Date(selectedTicket.created_at), "PPp")}</p>
                <p>Updated: {format(new Date(selectedTicket.updated_at), "PPp")}</p>
                {selectedTicket.resolved_at && (
                  <p>Resolved: {format(new Date(selectedTicket.resolved_at), "PPp")}</p>
                )}
                <p className="font-mono text-xs">ID: {selectedTicket.id}</p>
              </div>
            </div>
          </div>
        ) : (
          <ScrollArea className="h-[400px] pr-4">
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : tickets.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Ticket className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>You haven't submitted any tickets yet.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {tickets.map((ticket) => (
                  <button
                    key={ticket.id}
                    onClick={() => setSelectedTicket(ticket)}
                    className="w-full text-left p-4 rounded-lg border border-border hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-center gap-2 min-w-0">
                        {getTypeIcon(ticket.type)}
                        <span className="font-medium truncate">{ticket.title}</span>
                      </div>
                      {getStatusBadge(ticket.status)}
                    </div>
                    <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                      {getPriorityBadge(ticket.priority)}
                      <span>&bull;</span>
                      <span>{format(new Date(ticket.created_at), "MMM d, yyyy")}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </ScrollArea>
        )}
      </DialogContent>
    </Dialog>
  );
};
