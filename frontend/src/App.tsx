import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, useNavigate } from "react-router-dom";
import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import { PasswordReset } from "@/components/PasswordReset";
import ProjectDetailPage from "./pages/ProjectDetailPage";
import TicketsDashboard from "./pages/TicketsDashboard";
import FeedbackDashboard from "./pages/FeedbackDashboard";
import ProjectDashboard from "./pages/ProjectDashboard";
import EditAnalyticsDashboard from "./pages/EditAnalyticsDashboard";
import AdminSettings from "./pages/AdminSettings";
import PdfPopoutPage from "./pages/PdfPopoutPage";
import { useAuth, useAuthProvider, AuthContext } from "@/hooks/useAuth";
import { useUserRole } from "@/hooks/useUserRole";

const queryClient = new QueryClient();

// Auth-aware wrapper that provides user/role context to dashboard pages
const AuthenticatedWrapper = ({
  children,
}: {
  children: (props: { userId: string | null; isSupervisor: boolean; isAdmin: boolean }) => React.ReactNode;
}) => {
  const { user, isLoading } = useAuth();
  const userId = user?.id ?? null;
  const { isSupervisor, isAdmin, loading: roleLoading } = useUserRole(userId);

  if (isLoading || roleLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return <>{children({ userId, isSupervisor, isAdmin })}</>;
};

const TicketsDashboardWrapper = () => {
  const navigate = useNavigate();
  return (
    <AuthenticatedWrapper>
      {({ isSupervisor, isAdmin }) => (
        <TicketsDashboard
          onNavigateToProfile={() => navigate("/")}
          onNavigateToHome={() => navigate("/")}
          onNavigateToTickets={() => navigate("/tickets")}
          onNavigateToFeedback={() => navigate("/feedback")}
          onNavigateToAdminSettings={() => navigate("/admin-settings")}
          onSignOut={() => navigate("/")}
          isSupervisor={isSupervisor}
          isAdmin={isAdmin}
        />
      )}
    </AuthenticatedWrapper>
  );
};

const FeedbackDashboardWrapper = () => {
  const navigate = useNavigate();
  return (
    <AuthenticatedWrapper>
      {({ isSupervisor, isAdmin }) => (
        <FeedbackDashboard
          onNavigateToProfile={() => navigate("/")}
          onNavigateToHome={() => navigate("/")}
          onNavigateToTickets={() => navigate("/tickets")}
          onNavigateToAdminSettings={() => navigate("/admin-settings")}
          onSignOut={() => navigate("/")}
          isSupervisor={isSupervisor}
          isAdmin={isAdmin}
        />
      )}
    </AuthenticatedWrapper>
  );
};

const EditAnalyticsDashboardWrapper = () => {
  const navigate = useNavigate();
  return (
    <AuthenticatedWrapper>
      {({ isSupervisor, isAdmin }) => (
        <EditAnalyticsDashboard
          onNavigateToProfile={() => navigate("/")}
          onNavigateToHome={() => navigate("/")}
          onNavigateToTickets={() => navigate("/tickets")}
          onNavigateToFeedback={() => navigate("/feedback")}
          onNavigateToDashboard={() => navigate("/dashboard")}
          onNavigateToAnalytics={() => navigate("/analytics")}
          onNavigateToAdminSettings={() => navigate("/admin-settings")}
          onSignOut={() => navigate("/")}
          isSupervisor={isSupervisor}
          isAdmin={isAdmin}
        />
      )}
    </AuthenticatedWrapper>
  );
};

const AdminSettingsWrapper = () => {
  const navigate = useNavigate();
  return (
    <AuthenticatedWrapper>
      {({ isAdmin, isSupervisor }) => {
        if (!isAdmin) {
          navigate("/");
          return (
            <div className="min-h-screen bg-background flex items-center justify-center">
              <p className="text-muted-foreground">Redirecting...</p>
            </div>
          );
        }
        return (
          <AdminSettings
            onNavigateToProfile={() => navigate("/")}
            onNavigateToHome={() => navigate("/")}
            onNavigateToTickets={() => navigate("/tickets")}
            onNavigateToFeedback={() => navigate("/feedback")}
            onNavigateToDashboard={() => navigate("/dashboard")}
            onNavigateToAnalytics={() => navigate("/analytics")}
            onNavigateToAdminSettings={() => navigate("/admin-settings")}
            onSignOut={() => navigate("/")}
            isSupervisor={isSupervisor}
            isAdmin={isAdmin}
          />
        );
      }}
    </AuthenticatedWrapper>
  );
};

const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const auth = useAuthProvider();
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
};

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Index />} />
            <Route path="/reset-password" element={<PasswordReset />} />
            <Route path="/projects/:projectKey" element={<ProjectDetailPage />} />
            <Route path="/tickets" element={<TicketsDashboardWrapper />} />
            <Route path="/feedback" element={<FeedbackDashboardWrapper />} />
            <Route path="/dashboard" element={<ProjectDashboard />} />
            <Route path="/analytics" element={<EditAnalyticsDashboardWrapper />} />
            <Route path="/admin-settings" element={<AdminSettingsWrapper />} />
            <Route path="/pdf-preview" element={<PdfPopoutPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
