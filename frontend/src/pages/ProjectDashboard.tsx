import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import apiClient from "@/lib/apiClient";
import { useAuth } from "@/hooks/useAuth";
import { Navbar } from "@/components/Navbar";
import { useUserRole } from "@/hooks/useUserRole";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Clock,
  CheckCircle2,
  Users,
  Search,
  ArrowUpDown,
  ArrowLeft,
  FileText,
  User,
} from "lucide-react";
import { format } from "date-fns";

interface ProjectStats {
  pending: number;
  approved: number;
}

interface UserStats {
  user_id: string;
  full_name: string | null;
  email: string;
  submitted_count: number;
  pending_count: number;
  approved_count: number;
}

interface ProjectRow {
  project_hash: string;
  project_name: string | null;
  approval_status: string;
  submitted_by_full_name: string | null;
  submitted_by_user_id: string | null;
  submitted_at: string | null;
  approved_at: string | null;
  approved_by_full_name: string | null;
  finalized_by_full_name: string | null;
  finalized_by_user_id: string | null;
  finalized_at: string | null;
}

type SortField = "project_name" | "project_hash" | "approval_status" | "submitted_by_full_name" | "submitted_at" | "finalized_by_full_name" | "finalized_at";
type SortDirection = "asc" | "desc";

const ProjectDashboard = () => {
  const navigate = useNavigate();
  const { user, isLoading: authLoading } = useAuth();
  const userId = user?.id || null;
  const [loading, setLoading] = useState(true);
  const { isSupervisor, isAdmin } = useUserRole(userId);

  const [stats, setStats] = useState<ProjectStats>({ pending: 0, approved: 0 });
  const [userStats, setUserStats] = useState<UserStats[]>([]);
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [dataLoading, setDataLoading] = useState(true);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedUser, setSelectedUser] = useState<string>("all");
  const [selectedFinalizedUser, setSelectedFinalizedUser] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [submittedDateFrom, setSubmittedDateFrom] = useState<string>("");
  const [submittedDateTo, setSubmittedDateTo] = useState<string>("");
  const [finalizedDateFrom, setFinalizedDateFrom] = useState<string>("");
  const [finalizedDateTo, setFinalizedDateTo] = useState<string>("");

  // Sorting
  const [sortField, setSortField] = useState<SortField>("submitted_at");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  // User Summary expansion state
  const [showAllUsers, setShowAllUsers] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      navigate("/");
      return;
    }
    setLoading(false);
  }, [user, authLoading, navigate]);

  useEffect(() => {
    if (userId) {
      loadDashboardData();
    }
  }, [userId]);

  const loadDashboardData = async () => {
    setDataLoading(true);
    try {
      // Fetch all projects from the API
      // The backend listProjects endpoint returns projects with their details
      const projectsData = await apiClient.listProjects();

      // Handle the response - the API may return paginated data or an array
      const rawProjects = Array.isArray(projectsData) ? projectsData : (projectsData.items || projectsData.data || []);

      // Show all projects (including processing, submitted, approved, etc.)
      const filteredProjects = rawProjects;

      // Deduplicate by project_hash (keep first/most recent)
      const projectMap = new Map<string, ProjectRow>();
      filteredProjects.forEach((p: any) => {
        if (p.project_hash && !projectMap.has(p.project_hash)) {
          projectMap.set(p.project_hash, p as ProjectRow);
        }
      });
      const uniqueProjects = Array.from(projectMap.values());
      setProjects(uniqueProjects);

      // Calculate stats
      const pendingCount = uniqueProjects.filter(
        (p) => p.approval_status === "PENDING" || p.approval_status === "PENDING_APPROVAL" || p.approval_status === "CHANGES_REQUESTED"
      ).length;
      const approvedCount = uniqueProjects.filter((p) => p.approval_status === "APPROVED").length;

      // Fetch user list for user stats
      const usersData = await apiClient.listUsers();
      const profilesData = Array.isArray(usersData) ? usersData : (usersData.items || usersData.data || []);

      // Calculate per-user stats
      const userStatsMap = new Map<string, UserStats>();
      profilesData.forEach((profile: any) => {
        userStatsMap.set(profile.id, {
          user_id: profile.id,
          full_name: profile.full_name,
          email: profile.email,
          submitted_count: 0,
          pending_count: 0,
          approved_count: 0,
        });
      });

      // Count submissions, pending, and approvals per user
      uniqueProjects.forEach((project) => {
        if (project.submitted_by_user_id && userStatsMap.has(project.submitted_by_user_id)) {
          const userStat = userStatsMap.get(project.submitted_by_user_id)!;
          userStat.submitted_count++;
          if (project.approval_status === "APPROVED") {
            userStat.approved_count++;
          } else if (project.approval_status === "PENDING" || project.approval_status === "PENDING_APPROVAL" || project.approval_status === "CHANGES_REQUESTED") {
            userStat.pending_count++;
          }
        }
      });

      const userStatsArray = Array.from(userStatsMap.values()).sort((a, b) => {
        // Sort by submitted count desc, then by name
        if (b.submitted_count !== a.submitted_count) {
          return b.submitted_count - a.submitted_count;
        }
        return (a.full_name || a.email).localeCompare(b.full_name || b.email);
      });

      setUserStats(userStatsArray);
      setStats({ pending: pendingCount, approved: approvedCount });
    } catch (error) {
      console.error("Error loading dashboard data:", error);
    } finally {
      setDataLoading(false);
    }
  };

  // Get unique submitted users for filter dropdown (derived from projects, not profiles)
  const submittedUsers = useMemo(() => {
    const usersMap = new Map<string, { user_id: string; full_name: string | null }>();
    projects.forEach((p) => {
      if (p.submitted_by_user_id && p.submitted_by_full_name) {
        usersMap.set(p.submitted_by_user_id, {
          user_id: p.submitted_by_user_id,
          full_name: p.submitted_by_full_name,
        });
      }
    });
    return Array.from(usersMap.values()).sort((a, b) =>
      (a.full_name || "").localeCompare(b.full_name || "")
    );
  }, [projects]);

  // Get unique finalized users for filter dropdown
  const finalizedUsers = useMemo(() => {
    const usersMap = new Map<string, { user_id: string; full_name: string | null }>();
    projects.forEach((p) => {
      if (p.finalized_by_user_id && p.finalized_by_full_name) {
        usersMap.set(p.finalized_by_user_id, {
          user_id: p.finalized_by_user_id,
          full_name: p.finalized_by_full_name,
        });
      }
    });
    return Array.from(usersMap.values()).sort((a, b) =>
      (a.full_name || "").localeCompare(b.full_name || "")
    );
  }, [projects]);

  // Filter and sort projects
  const filteredProjects = useMemo(() => {
    let filtered = [...projects];

    // Search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (p) =>
          (p.project_name && p.project_name.toLowerCase().includes(query)) ||
          p.project_hash.toLowerCase().includes(query) ||
          (p.submitted_by_full_name && p.submitted_by_full_name.toLowerCase().includes(query)) ||
          (p.finalized_by_full_name && p.finalized_by_full_name.toLowerCase().includes(query))
      );
    }

    // Submitted User filter
    if (selectedUser !== "all") {
      filtered = filtered.filter((p) => p.submitted_by_user_id === selectedUser);
    }

    // Finalized User filter
    if (selectedFinalizedUser !== "all") {
      filtered = filtered.filter((p) => p.finalized_by_user_id === selectedFinalizedUser);
    }

    // Status filter
    if (statusFilter !== "all") {
      if (statusFilter === "pending") {
        filtered = filtered.filter(
          (p) => p.approval_status === "PENDING" || p.approval_status === "PENDING_APPROVAL" || p.approval_status === "CHANGES_REQUESTED"
        );
      } else if (statusFilter === "approved") {
        filtered = filtered.filter((p) => p.approval_status === "APPROVED");
      }
    }

    // Submitted Date Range filter
    if (submittedDateFrom) {
      const fromDate = new Date(submittedDateFrom);
      fromDate.setHours(0, 0, 0, 0);
      filtered = filtered.filter((p) => {
        if (!p.submitted_at) return false;
        return new Date(p.submitted_at) >= fromDate;
      });
    }
    if (submittedDateTo) {
      const toDate = new Date(submittedDateTo);
      toDate.setHours(23, 59, 59, 999);
      filtered = filtered.filter((p) => {
        if (!p.submitted_at) return false;
        return new Date(p.submitted_at) <= toDate;
      });
    }

    // Finalized Date Range filter
    if (finalizedDateFrom) {
      const fromDate = new Date(finalizedDateFrom);
      fromDate.setHours(0, 0, 0, 0);
      filtered = filtered.filter((p) => {
        if (!p.finalized_at) return false;
        return new Date(p.finalized_at) >= fromDate;
      });
    }
    if (finalizedDateTo) {
      const toDate = new Date(finalizedDateTo);
      toDate.setHours(23, 59, 59, 999);
      filtered = filtered.filter((p) => {
        if (!p.finalized_at) return false;
        return new Date(p.finalized_at) <= toDate;
      });
    }

    // Sorting
    filtered.sort((a, b) => {
      let aVal: string | null = null;
      let bVal: string | null = null;

      switch (sortField) {
        case "project_name":
          aVal = a.project_name || "";
          bVal = b.project_name || "";
          break;
        case "project_hash":
          aVal = a.project_hash;
          bVal = b.project_hash;
          break;
        case "approval_status":
          aVal = a.approval_status;
          bVal = b.approval_status;
          break;
        case "submitted_by_full_name":
          aVal = a.submitted_by_full_name || "";
          bVal = b.submitted_by_full_name || "";
          break;
        case "submitted_at":
          aVal = a.submitted_at || "";
          bVal = b.submitted_at || "";
          break;
        case "finalized_by_full_name":
          aVal = a.finalized_by_full_name || "";
          bVal = b.finalized_by_full_name || "";
          break;
        case "finalized_at":
          aVal = a.finalized_at || "";
          bVal = b.finalized_at || "";
          break;
      }

      const comparison = (aVal || "").localeCompare(bVal || "");
      return sortDirection === "asc" ? comparison : -comparison;
    });

    return filtered;
  }, [projects, searchQuery, selectedUser, selectedFinalizedUser, statusFilter, submittedDateFrom, submittedDateTo, finalizedDateFrom, finalizedDateTo, sortField, sortDirection]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDirection("asc");
    }
  };

  const handleProjectClick = (project: ProjectRow) => {
    navigate(`/projects/${project.project_hash}`);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "APPROVED":
        return <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30">Approved</Badge>;
      case "PENDING":
      case "PENDING_APPROVAL":
        return <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/30">Pending</Badge>;
      case "CHANGES_REQUESTED":
        return <Badge className="bg-orange-500/20 text-orange-400 border-orange-500/30">Changes Requested</Badge>;
      default:
        return <Badge variant="secondary">{status}</Badge>;
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Navbar
        onNavigateToProfile={() => navigate("/")}
        onNavigateToHome={() => navigate("/")}
        onNavigateToTickets={() => navigate("/tickets")}
        onNavigateToFeedback={() => navigate("/feedback")}
        onNavigateToDashboard={() => navigate("/dashboard")}
        onNavigateToAnalytics={() => navigate("/analytics")}
        onSignOut={() => navigate("/")}
        isSupervisor={isSupervisor}
        isAdmin={isAdmin}
      />

      <main className="container mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center gap-4 mb-8">
          <Button variant="ghost" size="sm" onClick={() => navigate("/")}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
          <div>
            <h1 className="text-3xl font-bold text-foreground">Projects Dashboard</h1>
            <p className="text-muted-foreground mt-1">Overview of all projects and user statistics</p>
          </div>
        </div>

        {dataLoading ? (
          <div className="flex items-center justify-center py-12">
            <p className="text-muted-foreground">Loading dashboard data...</p>
          </div>
        ) : (
          <div className="space-y-8">
            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <Card className="bg-card border-border">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">Pending Projects</CardTitle>
                  <Clock className="h-5 w-5 text-amber-500" />
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold text-foreground">{stats.pending}</div>
                  <p className="text-xs text-muted-foreground mt-1">Awaiting approval</p>
                </CardContent>
              </Card>

              <Card className="bg-card border-border">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">Approved Projects</CardTitle>
                  <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold text-foreground">{stats.approved}</div>
                  <p className="text-xs text-muted-foreground mt-1">Successfully completed</p>
                </CardContent>
              </Card>
            </div>

            {/* User Summary */}
            <Card className="bg-card border-border">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <User className="h-5 w-5" />
                  User Summary
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {userStats.slice(0, showAllUsers ? undefined : 3).map((user) => (
                    <div
                      key={user.user_id}
                      className={`p-4 rounded-lg border border-border ${
                        user.submitted_count > 0 ? "bg-muted/30" : "bg-muted/10 opacity-60"
                      } cursor-pointer hover:bg-muted/50 transition-colors`}
                      onClick={() => {
                        setSelectedUser(user.user_id);
                        setStatusFilter("all");
                      }}
                    >
                      <p className="font-medium text-foreground truncate">{user.full_name || user.email}</p>
                      <p className="text-xs text-muted-foreground truncate">{user.email}</p>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-sm">
                        <span className="text-muted-foreground">
                          Submitted: <span className="text-foreground font-medium">{user.submitted_count}</span>
                        </span>
                        <span className="text-muted-foreground">
                          Pending: <span className="text-amber-400 font-medium">{user.pending_count}</span>
                        </span>
                        <span className="text-muted-foreground">
                          Approved: <span className="text-emerald-400 font-medium">{user.approved_count}</span>
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
                {userStats.length > 3 && (
                  <button
                    onClick={() => setShowAllUsers(!showAllUsers)}
                    className="w-full text-center text-sm text-primary hover:text-primary/80 mt-4 py-2 transition-colors cursor-pointer"
                  >
                    {showAllUsers
                      ? "Show less"
                      : `And ${userStats.length - 3} more users...`}
                  </button>
                )}
              </CardContent>
            </Card>

            {/* Filters */}
            <Card className="bg-card border-border">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileText className="h-5 w-5" />
                  All Projects
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4 mb-6">
                  {/* Row 1: Search and dropdowns */}
                  <div className="flex flex-wrap gap-4">
                    <div className="flex-1 min-w-[200px]">
                      <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input
                          placeholder="Search by project name, ID, or user..."
                          value={searchQuery}
                          onChange={(e) => setSearchQuery(e.target.value)}
                          className="pl-9"
                        />
                      </div>
                    </div>
                    <Select value={selectedUser} onValueChange={setSelectedUser}>
                      <SelectTrigger className="w-[180px]">
                        <SelectValue placeholder="Submitted By" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Submitted By</SelectItem>
                        {submittedUsers.map((user) => (
                          <SelectItem key={user.user_id} value={user.user_id}>
                            {user.full_name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Select value={selectedFinalizedUser} onValueChange={setSelectedFinalizedUser}>
                      <SelectTrigger className="w-[180px]">
                        <SelectValue placeholder="Finalized By" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Finalized By</SelectItem>
                        {finalizedUsers.map((user) => (
                          <SelectItem key={user.user_id} value={user.user_id}>
                            {user.full_name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Select value={statusFilter} onValueChange={setStatusFilter}>
                      <SelectTrigger className="w-[150px]">
                        <SelectValue placeholder="Status" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Status</SelectItem>
                        <SelectItem value="pending">Pending</SelectItem>
                        <SelectItem value="approved">Approved</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Row 2: Date filters */}
                  <div className="flex flex-wrap gap-4 items-center">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-muted-foreground whitespace-nowrap">Submitted:</span>
                      <Input
                        type="date"
                        value={submittedDateFrom}
                        onChange={(e) => setSubmittedDateFrom(e.target.value)}
                        className="w-[140px]"
                        placeholder="From"
                      />
                      <span className="text-muted-foreground">-</span>
                      <Input
                        type="date"
                        value={submittedDateTo}
                        onChange={(e) => setSubmittedDateTo(e.target.value)}
                        className="w-[140px]"
                        placeholder="To"
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-muted-foreground whitespace-nowrap">Finalized:</span>
                      <Input
                        type="date"
                        value={finalizedDateFrom}
                        onChange={(e) => setFinalizedDateFrom(e.target.value)}
                        className="w-[140px]"
                        placeholder="From"
                      />
                      <span className="text-muted-foreground">-</span>
                      <Input
                        type="date"
                        value={finalizedDateTo}
                        onChange={(e) => setFinalizedDateTo(e.target.value)}
                        className="w-[140px]"
                        placeholder="To"
                      />
                    </div>
                    {(searchQuery || selectedUser !== "all" || selectedFinalizedUser !== "all" || statusFilter !== "all" || submittedDateFrom || submittedDateTo || finalizedDateFrom || finalizedDateTo) && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setSearchQuery("");
                          setSelectedUser("all");
                          setSelectedFinalizedUser("all");
                          setStatusFilter("all");
                          setSubmittedDateFrom("");
                          setSubmittedDateTo("");
                          setFinalizedDateFrom("");
                          setFinalizedDateTo("");
                        }}
                      >
                        Clear Filters
                      </Button>
                    )}
                  </div>
                </div>

                {/* Projects Table */}
                <div className="rounded-lg border border-border overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-muted/30">
                        <TableHead
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() => handleSort("project_name")}
                        >
                          <div className="flex items-center gap-2">
                            Project Name
                            <ArrowUpDown className="h-3 w-3" />
                          </div>
                        </TableHead>
                        <TableHead
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() => handleSort("approval_status")}
                        >
                          <div className="flex items-center gap-2">
                            Status
                            <ArrowUpDown className="h-3 w-3" />
                          </div>
                        </TableHead>
                        <TableHead
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() => handleSort("submitted_by_full_name")}
                        >
                          <div className="flex items-center gap-2">
                            Submitted By
                            <ArrowUpDown className="h-3 w-3" />
                          </div>
                        </TableHead>
                        <TableHead
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() => handleSort("submitted_at")}
                        >
                          <div className="flex items-center gap-2">
                            Submitted At
                            <ArrowUpDown className="h-3 w-3" />
                          </div>
                        </TableHead>
                        <TableHead
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() => handleSort("finalized_by_full_name")}
                        >
                          <div className="flex items-center gap-2">
                            Finalized By
                            <ArrowUpDown className="h-3 w-3" />
                          </div>
                        </TableHead>
                        <TableHead
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() => handleSort("finalized_at")}
                        >
                          <div className="flex items-center gap-2">
                            Finalized At
                            <ArrowUpDown className="h-3 w-3" />
                          </div>
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredProjects.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                            No projects found matching your criteria
                          </TableCell>
                        </TableRow>
                      ) : (
                        filteredProjects.map((project) => (
                          <TableRow
                            key={project.project_hash}
                            className="cursor-pointer hover:bg-muted/30 transition-colors"
                            onClick={() => handleProjectClick(project)}
                          >
                            <TableCell className="font-medium">
                              {project.project_name || "Unnamed Project"}
                            </TableCell>
                            <TableCell>{getStatusBadge(project.approval_status)}</TableCell>
                            <TableCell>{project.submitted_by_full_name || "-"}</TableCell>
                            <TableCell className="text-muted-foreground">
                              {project.submitted_at
                                ? format(new Date(project.submitted_at), "MMM d, yyyy")
                                : "-"}
                            </TableCell>
                            <TableCell>{project.finalized_by_full_name || "-"}</TableCell>
                            <TableCell className="text-muted-foreground">
                              {project.finalized_at
                                ? format(new Date(project.finalized_at), "MMM d, yyyy")
                                : "-"}
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </div>

                <div className="mt-4 text-sm text-muted-foreground">
                  Showing {filteredProjects.length} of {projects.length} projects
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </main>
    </div>
  );
};

export default ProjectDashboard;
