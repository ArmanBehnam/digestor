import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import apiClient from "@/lib/apiClient";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { User, KeyRound, Trash2, LogOut } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

interface ProfileData {
  full_name: string;
  email: string;
}

export const Profile = ({ onSignOut }: { onSignOut: () => void }) => {
  const { user, logout } = useAuth();
  const [profile, setProfile] = useState<ProfileData>({
    full_name: user?.full_name || "",
    email: user?.email || "",
  });
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const { toast } = useToast();

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      await apiClient.updateProfile({ full_name: profile.full_name });

      toast({
        title: "Profile updated",
        description: "Your profile has been updated successfully.",
      });
    } catch (error: any) {
      toast({
        title: "Update failed",
        description: error.message,
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      if (newPassword !== confirmPassword) {
        throw new Error("Passwords do not match");
      }

      if (newPassword.length < 8) {
        throw new Error("Password must be at least 8 characters");
      }

      await apiClient.changePassword(newPassword);

      toast({
        title: "Password changed",
        description: "Your password has been updated successfully.",
      });

      setNewPassword("");
      setConfirmPassword("");
    } catch (error: any) {
      toast({
        title: "Password change failed",
        description: error.message,
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAccount = async () => {
    setDeleting(true);
    try {
      await apiClient.deleteAccount();
      await logout();

      toast({
        title: "Account deletion requested",
        description: "Your account deletion request has been submitted.",
      });

      onSignOut();
    } catch (error: any) {
      toast({
        title: "Deletion failed",
        description: error.message,
        variant: "destructive",
      });
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold text-foreground">Profile Settings</h1>
          <Button variant="outline" onClick={onSignOut}>
            <LogOut className="mr-2 h-4 w-4" />
            Sign Out
          </Button>
        </div>

        {/* Profile Information */}
        <Card className="p-6 bg-gradient-card border-border">
          <div className="flex items-center gap-2 mb-4">
            <User className="h-5 w-5 text-primary" />
            <h2 className="text-xl font-semibold text-foreground">
              Profile Information
            </h2>
          </div>
          <form onSubmit={handleUpdateProfile} className="space-y-4">
            <div>
              <Label htmlFor="fullName">Full Name</Label>
              <Input
                id="fullName"
                type="text"
                value={profile.full_name}
                onChange={(e) =>
                  setProfile({ ...profile, full_name: e.target.value })
                }
                disabled={loading}
                className="bg-background/50"
              />
            </div>
            <div>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={profile.email}
                disabled
                className="bg-background/50"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Email cannot be changed
              </p>
            </div>
            <Button type="submit" disabled={loading}>
              {loading ? "Saving..." : "Save Changes"}
            </Button>
          </form>
        </Card>

        {/* Change Password */}
        <Card className="p-6 bg-gradient-card border-border">
          <div className="flex items-center gap-2 mb-4">
            <KeyRound className="h-5 w-5 text-primary" />
            <h2 className="text-xl font-semibold text-foreground">
              Change Password
            </h2>
          </div>
          <form onSubmit={handleChangePassword} className="space-y-4">
            <div>
              <Label htmlFor="newPassword">New Password</Label>
              <Input
                id="newPassword"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                disabled={loading}
                className="bg-background/50"
                placeholder="Min 8 characters, 1 number, 1 letter"
              />
            </div>
            <div>
              <Label htmlFor="confirmPassword">Confirm New Password</Label>
              <Input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                disabled={loading}
                className="bg-background/50"
              />
            </div>
            <Button type="submit" disabled={loading}>
              {loading ? "Updating..." : "Update Password"}
            </Button>
          </form>
        </Card>

        {/* Account Actions */}
        <Card className="p-6 bg-gradient-card border-border">
          <h2 className="text-xl font-semibold text-foreground mb-4">
            Account Actions
          </h2>
          <div className="space-y-3">
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  variant="destructive"
                  className="w-full justify-start"
                  disabled={deleting}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  Delete Account
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This action cannot be undone. This will permanently delete your
                    account and remove your data from our servers.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleDeleteAccount}>
                    Delete Account
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </Card>
      </div>
    </div>
  );
};
