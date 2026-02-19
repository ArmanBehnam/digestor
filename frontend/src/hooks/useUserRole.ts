import { useState, useEffect } from "react";
import { useAuth } from "@/hooks/useAuth";

export type UserRole = "user" | "admin" | "supervisor";

export function useUserRole(userId: string | null) {
  const { user } = useAuth();
  const [role, setRole] = useState<UserRole | null>(null);
  const [isSupervisor, setIsSupervisor] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);

    if (!userId || !user) {
      setRole(null);
      setIsSupervisor(false);
      setIsAdmin(false);
      setLoading(false);
      return;
    }

    try {
      // Roles come from Cognito groups via the useAuth hook
      const groups = user.groups || [];
      const userRole = user.role || "engineer";

      const hasAdmin = groups.includes("admin") || userRole === "admin";
      const hasSupervisor = groups.includes("supervisor") || userRole === "supervisor";

      setIsAdmin(hasAdmin);
      setIsSupervisor(hasSupervisor);

      if (hasAdmin) {
        setRole("admin");
      } else if (hasSupervisor) {
        setRole("supervisor");
      } else {
        setRole("user");
      }
    } catch (error) {
      console.error("Error in useUserRole:", error);
      setRole("user");
      setIsSupervisor(false);
      setIsAdmin(false);
    } finally {
      setLoading(false);
    }
  }, [userId, user]);

  return { role, isSupervisor, isAdmin, loading };
}
