import { useState, useEffect } from "react";
import apiClient from "@/lib/apiClient";
import { Navbar } from "@/components/Navbar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2, Search, Star, FileText, Users, ClipboardList, ArrowLeft } from "lucide-react";
import { format } from "date-fns";

interface FeedbackDashboardProps {
  onNavigateToProfile: () => void;
  onNavigateToHome: () => void;
  onNavigateToTickets?: () => void;
  onNavigateToAdminSettings?: () => void;
  onSignOut: () => void;
  isSupervisor?: boolean;
  isAdmin?: boolean;
}

interface FeedbackEntry {
  id: string;
  user_id: string;
  user_email: string;
  user_name: string | null;
  status: "draft" | "submitted";
  role_position: string | null;
  painful_part: string | null;
  what_surprised: string | null;
  expected_not_do: string | null;
  confusing_part: string | null;
  overall_satisfaction: number | null;
  specific_project_issue: string | null;
  other_comments: string | null;
  contact_for_followup: string | null;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
}

const satisfactionLabels: Record<number, string> = {
  1: "Very poor",
  2: "Poor",
  3: "Fair",
  4: "Good",
  5: "Excellent",
};

const FeedbackDashboard = ({
  onNavigateToProfile,
  onNavigateToHome,
  onNavigateToTickets,
  onNavigateToAdminSettings,
  onSignOut,
  isSupervisor = false,
  isAdmin = false,
}: FeedbackDashboardProps) => {
  const [feedback, setFeedback] = useState<FeedbackEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedFeedback, setSelectedFeedback] = useState<FeedbackEntry | null>(null);

  useEffect(() => {
    loadFeedback();
  }, []);

  const loadFeedback = async () => {
    setLoading(true);
    try {
      const data = await apiClient.listAllFeedback();
      setFeedback((data as FeedbackEntry[]) || []);
    } catch (error: any) {
      console.error("Error loading feedback:", error);
    } finally {
      setLoading(false);
    }
  };

  const filteredFeedback = feedback.filter((entry) => {
    const matchesSearch =
      entry.user_email.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (entry.user_name?.toLowerCase() || "").includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === "all" || entry.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const submittedCount = feedback.filter((f) => f.status === "submitted").length;
  const draftCount = feedback.filter((f) => f.status === "draft").length;
  const avgSatisfaction =
    submittedCount > 0
      ? feedback
          .filter((f) => f.status === "submitted" && f.overall_satisfaction)
          .reduce((sum, f) => sum + (f.overall_satisfaction || 0), 0) /
        feedback.filter((f) => f.status === "submitted" && f.overall_satisfaction).length
      : 0;

  const renderSatisfactionBadge = (rating: number | null) => {
    if (!rating) return <span className="text-muted-foreground">N/A</span>;
    const colors: Record<number, string> = {
      1: "bg-red-100 text-red-800",
      2: "bg-orange-100 text-orange-800",
      3: "bg-yellow-100 text-yellow-800",
      4: "bg-green-100 text-green-800",
      5: "bg-emerald-100 text-emerald-800",
    };
    return (
      <Badge className={colors[rating]}>
        {rating} - {satisfactionLabels[rating]}
      </Badge>
    );
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar
        onNavigateToProfile={onNavigateToProfile}
        onNavigateToHome={onNavigateToHome}
        onNavigateToTickets={onNavigateToTickets}
        onNavigateToAdminSettings={onNavigateToAdminSettings}
        onSignOut={onSignOut}
        isSupervisor={isSupervisor}
        isAdmin={isAdmin}
      />

      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center gap-4 mb-6">
          <Button variant="ghost" onClick={onNavigateToHome}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
          <h1 className="text-2xl font-bold">Feedback Dashboard</h1>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Responses</CardTitle>
              <ClipboardList className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{feedback.length}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Submitted</CardTitle>
              <FileText className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-green-600">{submittedCount}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Drafts</CardTitle>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-yellow-600">{draftCount}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Avg. Satisfaction</CardTitle>
              <Star className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {avgSatisfaction > 0 ? avgSatisfaction.toFixed(1) : "N/A"}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Filters */}
        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by email or name..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-full sm:w-[180px]">
              <SelectValue placeholder="Filter by status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="submitted">Submitted</SelectItem>
              <SelectItem value="draft">Draft</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Feedback Table */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : filteredFeedback.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <p className="text-muted-foreground">No feedback found.</p>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>User</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Satisfaction</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredFeedback.map((entry) => (
                    <TableRow key={entry.id}>
                      <TableCell>
                        <div>
                          <p className="font-medium">{entry.user_name || "Unknown"}</p>
                          <p className="text-sm text-muted-foreground">{entry.user_email}</p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm">
                          {entry.role_position
                            ? entry.role_position.length > 30
                              ? `${entry.role_position.substring(0, 30)}...`
                              : entry.role_position
                            : "-"}
                        </span>
                      </TableCell>
                      <TableCell>{renderSatisfactionBadge(entry.overall_satisfaction)}</TableCell>
                      <TableCell>
                        <Badge
                          variant={entry.status === "submitted" ? "default" : "secondary"}
                        >
                          {entry.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {format(
                          new Date(entry.submitted_at || entry.created_at),
                          "MMM d, yyyy"
                        )}
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setSelectedFeedback(entry)}
                        >
                          View Details
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Detail Dialog */}
      <Dialog open={!!selectedFeedback} onOpenChange={() => setSelectedFeedback(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Feedback Details</DialogTitle>
          </DialogHeader>
          {selectedFeedback && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4 pb-4 border-b">
                <div>
                  <p className="text-sm text-muted-foreground">User</p>
                  <p className="font-medium">{selectedFeedback.user_name || "Unknown"}</p>
                  <p className="text-sm">{selectedFeedback.user_email}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Status</p>
                  <Badge
                    variant={selectedFeedback.status === "submitted" ? "default" : "secondary"}
                  >
                    {selectedFeedback.status}
                  </Badge>
                  <p className="text-sm mt-1">
                    {selectedFeedback.submitted_at
                      ? `Submitted: ${format(new Date(selectedFeedback.submitted_at), "PPpp")}`
                      : `Last updated: ${format(new Date(selectedFeedback.updated_at), "PPpp")}`}
                  </p>
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">1. Role / Position</p>
                  <p>{selectedFeedback.role_position || "-"}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">2. Most Painful Part</p>
                  <p>{selectedFeedback.painful_part || "-"}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">3. What Surprised You</p>
                  <p>{selectedFeedback.what_surprised || "-"}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    4. Expected but Not Done
                  </p>
                  <p>{selectedFeedback.expected_not_do || "-"}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">5. Confusing Parts</p>
                  <p>{selectedFeedback.confusing_part || "-"}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    6. Overall Satisfaction
                  </p>
                  {renderSatisfactionBadge(selectedFeedback.overall_satisfaction)}
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    7. Specific Project Issue
                  </p>
                  <p>{selectedFeedback.specific_project_issue || "-"}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">8. Other Comments</p>
                  <p>{selectedFeedback.other_comments || "-"}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">9. Contact for Follow-up</p>
                  <p>{selectedFeedback.contact_for_followup || "-"}</p>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default FeedbackDashboard;
