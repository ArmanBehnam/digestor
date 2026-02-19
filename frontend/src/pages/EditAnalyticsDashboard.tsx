import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import apiClient from "@/lib/apiClient";
import { Navbar } from "@/components/Navbar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  ArrowLeft,
  Search,
  PenLine,
  FileText,
  Users,
  BarChart3,
  HelpCircle,
  ArrowUpDown,
  Loader2,
} from "lucide-react";
import { format } from "date-fns";

interface EditAnalyticsDashboardProps {
  onNavigateToProfile: () => void;
  onNavigateToHome: () => void;
  onNavigateToTickets?: () => void;
  onNavigateToFeedback?: () => void;
  onNavigateToDashboard?: () => void;
  onNavigateToAnalytics?: () => void;
  onNavigateToAdminSettings?: () => void;
  onSignOut: () => void;
  isSupervisor?: boolean;
  isAdmin?: boolean;
}

interface QuestionStats {
  question_id: number | null;
  question_text: string | null;
  edit_count: number;
  projects_affected: number;
}

interface ProjectEditStats {
  project_hash: string;
  project_name: string | null;
  total_edits: number;
  questions_edited: number;
  editors: number;
  last_edit_at: string | null;
}

type SortField = "project_name" | "total_edits" | "questions_edited" | "editors" | "last_edit_at";
type SortDirection = "asc" | "desc";

const EditAnalyticsDashboard = ({
  onNavigateToProfile,
  onNavigateToHome,
  onNavigateToTickets,
  onNavigateToFeedback,
  onNavigateToDashboard,
  onNavigateToAnalytics,
  onNavigateToAdminSettings,
  onSignOut,
  isSupervisor = false,
  isAdmin = false,
}: EditAnalyticsDashboardProps) => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [sortField, setSortField] = useState<SortField>("total_edits");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  // Stats
  const [totalEdits, setTotalEdits] = useState(0);
  const [projectsWithEdits, setProjectsWithEdits] = useState(0);
  const [totalEditors, setTotalEditors] = useState(0);
  const [avgEditsPerProject, setAvgEditsPerProject] = useState(0);

  // Data
  const [questionStats, setQuestionStats] = useState<QuestionStats[]>([]);
  const [projectStats, setProjectStats] = useState<ProjectEditStats[]>([]);

  useEffect(() => {
    loadAnalytics();
  }, []);

  const loadAnalytics = async () => {
    setLoading(true);
    try {
      // Fetch edit analytics from the backend API
      // The backend aggregates this data server-side
      const data = await apiClient.getEditAnalytics();

      // The backend returns pre-computed analytics data
      // Expected shape: { total_edits, projects_with_edits, total_editors, avg_edits_per_project, question_stats, project_stats }
      if (data) {
        setTotalEdits(data.total_edits || 0);
        setProjectsWithEdits(data.projects_with_edits || 0);
        setTotalEditors(data.total_editors || 0);
        setAvgEditsPerProject(data.avg_edits_per_project || 0);
        setQuestionStats((data.question_stats || []) as QuestionStats[]);
        setProjectStats((data.project_stats || []) as ProjectEditStats[]);
      }
    } catch (error) {
      console.error("Error loading analytics:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  };

  const filteredAndSortedProjects = useMemo(() => {
    let filtered = [...projectStats];

    // Search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (p) =>
          (p.project_name && p.project_name.toLowerCase().includes(query)) ||
          p.project_hash.toLowerCase().includes(query)
      );
    }

    // Sort
    filtered.sort((a, b) => {
      let aVal: string | number = 0;
      let bVal: string | number = 0;

      switch (sortField) {
        case "project_name":
          aVal = a.project_name || a.project_hash;
          bVal = b.project_name || b.project_hash;
          break;
        case "total_edits":
          aVal = a.total_edits;
          bVal = b.total_edits;
          break;
        case "questions_edited":
          aVal = a.questions_edited;
          bVal = b.questions_edited;
          break;
        case "editors":
          aVal = a.editors;
          bVal = b.editors;
          break;
        case "last_edit_at":
          aVal = a.last_edit_at || "";
          bVal = b.last_edit_at || "";
          break;
      }

      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortDirection === "asc" ? aVal - bVal : bVal - aVal;
      }
      const comparison = String(aVal).localeCompare(String(bVal));
      return sortDirection === "asc" ? comparison : -comparison;
    });

    return filtered;
  }, [projectStats, searchQuery, sortField, sortDirection]);

  const handleProjectClick = (projectHash: string) => {
    navigate(`/projects/${projectHash}`);
  };

  const SortableHeader = ({ field, children }: { field: SortField; children: React.ReactNode }) => (
    <TableHead
      className="cursor-pointer hover:bg-muted/50 transition-colors"
      onClick={() => handleSort(field)}
    >
      <div className="flex items-center gap-1">
        {children}
        <ArrowUpDown className={`h-3 w-3 ${sortField === field ? "text-primary" : "text-muted-foreground"}`} />
      </div>
    </TableHead>
  );

  return (
    <div className="min-h-screen bg-background">
      <Navbar
        onNavigateToProfile={onNavigateToProfile}
        onNavigateToHome={onNavigateToHome}
        onNavigateToTickets={onNavigateToTickets}
        onNavigateToFeedback={onNavigateToFeedback}
        onNavigateToDashboard={onNavigateToDashboard}
        onNavigateToAnalytics={onNavigateToAnalytics}
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
          <div>
            <h1 className="text-2xl font-bold">Edit Analytics Dashboard</h1>
            <p className="text-sm text-muted-foreground">Monitor normalized answer edits across projects</p>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : (
          <div className="space-y-6">
            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">Total Edits</CardTitle>
                  <PenLine className="h-4 w-4 text-primary" />
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">{totalEdits}</div>
                  <p className="text-xs text-muted-foreground mt-1">Normalized answer changes</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">Projects with Edits</CardTitle>
                  <FileText className="h-4 w-4 text-amber-500" />
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">{projectsWithEdits}</div>
                  <p className="text-xs text-muted-foreground mt-1">Approved/pending projects with edits</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">Avg Edits/Project</CardTitle>
                  <BarChart3 className="h-4 w-4 text-emerald-500" />
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">{avgEditsPerProject.toFixed(1)}</div>
                  <p className="text-xs text-muted-foreground mt-1">Per edited project</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">Total Editors</CardTitle>
                  <Users className="h-4 w-4 text-blue-500" />
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">{totalEditors}</div>
                  <p className="text-xs text-muted-foreground mt-1">Unique users</p>
                </CardContent>
              </Card>
            </div>

            {/* Most Edited Questions */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <HelpCircle className="h-5 w-5" />
                  Most Frequently Edited Questions
                </CardTitle>
              </CardHeader>
              <CardContent>
                {questionStats.length === 0 ? (
                  <p className="text-muted-foreground text-center py-8">No edits recorded yet.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-12">#</TableHead>
                          <TableHead>Question</TableHead>
                          <TableHead className="text-right">Edit Count</TableHead>
                          <TableHead className="text-right">Projects Affected</TableHead>
                          <TableHead className="text-right">% of Projects</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {questionStats.slice(0, 10).map((stat, index) => (
                          <TableRow key={`${stat.question_id}-${index}`}>
                            <TableCell className="font-medium text-muted-foreground">
                              {stat.question_id !== null ? `Q${stat.question_id}` : "-"}
                            </TableCell>
                            <TableCell className="max-w-md">
                              <span className="line-clamp-2" title={stat.question_text || ""}>
                                {stat.question_text || "Unknown question"}
                              </span>
                            </TableCell>
                            <TableCell className="text-right">
                              <Badge variant="secondary">{stat.edit_count}</Badge>
                            </TableCell>
                            <TableCell className="text-right">{stat.projects_affected}</TableCell>
                            <TableCell className="text-right">
                              {projectsWithEdits > 0
                                ? `${((stat.projects_affected / projectsWithEdits) * 100).toFixed(0)}%`
                                : "0%"}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Edits by Project */}
            <Card>
              <CardHeader>
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <CardTitle className="flex items-center gap-2">
                    <FileText className="h-5 w-5" />
                    Edits by Project
                  </CardTitle>
                  <div className="relative w-full sm:w-64">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="Search projects..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-10"
                    />
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {filteredAndSortedProjects.length === 0 ? (
                  <p className="text-muted-foreground text-center py-8">
                    {searchQuery ? "No projects match your search." : "No projects with edits."}
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <SortableHeader field="project_name">Project</SortableHeader>
                          <SortableHeader field="total_edits">Total Edits</SortableHeader>
                          <SortableHeader field="questions_edited">Questions</SortableHeader>
                          <SortableHeader field="editors">Editors</SortableHeader>
                          <SortableHeader field="last_edit_at">Last Edit</SortableHeader>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredAndSortedProjects.map((project) => (
                          <TableRow
                            key={project.project_hash}
                            className="cursor-pointer hover:bg-muted/50"
                            onClick={() => handleProjectClick(project.project_hash)}
                          >
                            <TableCell className="font-medium max-w-xs truncate">
                              {project.project_name || "Unnamed Project"}
                            </TableCell>
                            <TableCell>
                              <Badge className="bg-primary/20 text-primary border-primary/30">
                                {project.total_edits}
                              </Badge>
                            </TableCell>
                            <TableCell>{project.questions_edited}</TableCell>
                            <TableCell>{project.editors}</TableCell>
                            <TableCell className="text-muted-foreground text-sm">
                              {project.last_edit_at
                                ? format(new Date(project.last_edit_at), "MMM d, yyyy")
                                : "-"}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
};

export default EditAnalyticsDashboard;
