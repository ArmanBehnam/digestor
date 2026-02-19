import { useState, useEffect } from "react";
import apiClient from "@/lib/apiClient";
import { useAuth } from "@/hooks/useAuth";
import { Navbar } from "@/components/Navbar";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/hooks/use-toast";
import { Shield, UserPlus, Users, Search, X, Loader2 } from "lucide-react";

interface NavbarProps {
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

interface AdminSettingsProps extends NavbarProps {}

interface UserWithRoles {
  id: string;
  email: string;
  full_name: string | null;
  roles: Array<"user" | "admin" | "supervisor">;
}

export default function AdminSettings({
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
}: AdminSettingsProps) {
  const [users, setUsers] = useState<UserWithRoles[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [newRoleEmail, setNewRoleEmail] = useState("");
  const [selectedRole, setSelectedRole] = useState<"user" | "admin" | "supervisor">("user");
  const [addingRole, setAddingRole] = useState(false);
  const [removingRole, setRemovingRole] = useState<string | null>(null);
  const { toast } = useToast();
  const { user } = useAuth();

  useEffect(() => {
    loadUsersWithRoles();
  }, []);

  const loadUsersWithRoles = async () => {
    setLoading(true);
    try {
      // Fetch all users with their roles from the admin API
      const data = await apiClient.listUsers();
      const usersData = Array.isArray(data) ? data : (data.items || data.data || []);

      // Map to expected shape - the backend may return roles inline or separately
      const usersWithRoles: UserWithRoles[] = usersData.map((u: any) => ({
        id: u.id,
        email: u.email,
        full_name: u.full_name,
        roles: u.roles || [],
      }));

      setUsers(usersWithRoles);
    } catch (error: any) {
      toast({
        title: "Error loading users",
        description: error.message,
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleAddRole = async () => {
    if (!newRoleEmail.trim()) {
      toast({
        title: "Email required",
        description: "Please enter a user's email address.",
        variant: "destructive",
      });
      return;
    }

    setAddingRole(true);
    try {
      // Find user by email in the current users list
      const targetUser = users.find(
        (u) => u.email.toLowerCase() === newRoleEmail.trim().toLowerCase()
      );

      if (!targetUser) {
        toast({
          title: "User not found",
          description: "No user found with that email address. The user must sign up first.",
          variant: "destructive",
        });
        return;
      }

      // Check if user already has this role
      if (targetUser.roles.includes(selectedRole)) {
        toast({
          title: "Role already assigned",
          description: `${targetUser.full_name || targetUser.email} already has the ${selectedRole} role.`,
          variant: "destructive",
        });
        return;
      }

      // Add the role via backend API
      // Backend handles audit logging
      await apiClient.updateUserRole(targetUser.id, selectedRole);

      toast({
        title: "Role added",
        description: `${selectedRole} role added to ${targetUser.full_name || targetUser.email}.`,
      });

      setNewRoleEmail("");
      loadUsersWithRoles();
    } catch (error: any) {
      toast({
        title: "Error adding role",
        description: error.message,
        variant: "destructive",
      });
    } finally {
      setAddingRole(false);
    }
  };

  const handleRemoveRole = async (userId: string, role: "user" | "admin" | "supervisor") => {
    const targetUser = users.find((u) => u.id === userId);
    if (!targetUser) return;

    // Safety check: prevent removing the last admin
    if (role === "admin") {
      const adminCount = users.filter((u) => u.roles.includes("admin")).length;
      if (adminCount <= 1) {
        toast({
          title: "Cannot remove role",
          description: "Cannot remove the last admin. At least one admin must exist.",
          variant: "destructive",
        });
        return;
      }
    }

    setRemovingRole(`${userId}-${role}`);
    try {
      // Backend handles role removal and audit logging
      // We pass a special remove directive to the updateUserRole endpoint
      await apiClient.updateUserRole(userId, `remove:${role}`);

      toast({
        title: "Role removed",
        description: `${role} role removed from ${targetUser.full_name || targetUser.email}.`,
      });

      loadUsersWithRoles();
    } catch (error: any) {
      toast({
        title: "Error removing role",
        description: error.message,
        variant: "destructive",
      });
    } finally {
      setRemovingRole(null);
    }
  };

  const filteredUsers = users.filter(
    (user) =>
      user.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (user.full_name && user.full_name.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const getRoleBadgeVariant = (role: string) => {
    switch (role) {
      case "admin":
        return "destructive";
      case "supervisor":
        return "default";
      default:
        return "secondary";
    }
  };

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

      <div className="container mx-auto px-4 py-8 max-w-5xl">
        <div className="flex items-center gap-3 mb-8">
          <Shield className="h-8 w-8 text-primary" />
          <div>
            <h1 className="text-3xl font-bold">Admin Settings</h1>
            <p className="text-muted-foreground">Manage user roles and permissions</p>
          </div>
        </div>

        {/* Add Role Section */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UserPlus className="h-5 w-5" />
              Add Role to User
            </CardTitle>
            <CardDescription>
              Enter a user's email address to assign them a role. The user must have signed up first.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col sm:flex-row gap-4">
              <Input
                placeholder="Enter email address..."
                value={newRoleEmail}
                onChange={(e) => setNewRoleEmail(e.target.value)}
                className="flex-1"
                type="email"
              />
              <Select value={selectedRole} onValueChange={(value: "user" | "admin" | "supervisor") => setSelectedRole(value)}>
                <SelectTrigger className="w-full sm:w-40">
                  <SelectValue placeholder="Select role" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">User</SelectItem>
                  <SelectItem value="supervisor">Supervisor</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
              <Button onClick={handleAddRole} disabled={addingRole}>
                {addingRole ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Adding...
                  </>
                ) : (
                  "Add Role"
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Users List Section */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              All Users ({users.length})
            </CardTitle>
            <CardDescription>View and manage roles for all registered users</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="mb-4">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search by email or name..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>

            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Email</TableHead>
                      <TableHead>Name</TableHead>
                      <TableHead>Roles</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredUsers.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3} className="text-center text-muted-foreground py-8">
                          No users found
                        </TableCell>
                      </TableRow>
                    ) : (
                      filteredUsers.map((user) => (
                        <TableRow key={user.id}>
                          <TableCell className="font-medium">{user.email}</TableCell>
                          <TableCell>{user.full_name || "-"}</TableCell>
                          <TableCell>
                            <div className="flex flex-wrap gap-2">
                              {user.roles.length === 0 ? (
                                <span className="text-muted-foreground text-sm">No roles</span>
                              ) : (
                                user.roles.map((role) => (
                                  <Badge
                                    key={role}
                                    variant={getRoleBadgeVariant(role)}
                                    className="flex items-center gap-1"
                                  >
                                    {role}
                                    <button
                                      onClick={() => handleRemoveRole(user.id, role)}
                                      disabled={removingRole === `${user.id}-${role}`}
                                      className="ml-1 hover:bg-black/20 rounded-full p-0.5"
                                      title={`Remove ${role} role`}
                                    >
                                      {removingRole === `${user.id}-${role}` ? (
                                        <Loader2 className="h-3 w-3 animate-spin" />
                                      ) : (
                                        <X className="h-3 w-3" />
                                      )}
                                    </button>
                                  </Badge>
                                ))
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
