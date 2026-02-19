import { useParams, useSearchParams, useNavigate } from "react-router-dom";
import { ProjectDetail } from "@/components/ProjectDetail";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useUserRole } from "@/hooks/useUserRole";

const ProjectDetailPage = () => {
  const { projectKey } = useParams<{ projectKey: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const version = searchParams.get("version");
  const { user } = useAuth();

  const { isAdmin, isSupervisor } = useUserRole(user?.id || null);

  const handleBack = () => {
    navigate("/");
  };

  if (!projectKey) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <p className="text-muted-foreground">Invalid project URL</p>
          <Button onClick={handleBack} className="mt-4">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Go Home
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="px-4 py-8 w-full">
        <ProjectDetail
          projectHash={projectKey}
          onBack={handleBack}
          requestedVersion={version ? parseInt(version) : undefined}
          isAdmin={isAdmin}
          isSupervisorProp={isSupervisor}
        />
      </div>
    </div>
  );
};

export default ProjectDetailPage;
