import { useState } from "react";
import apiClient from "@/lib/apiClient";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { LogIn } from "lucide-react";
import { z } from "zod";

const passwordSchema = z
  .string()
  .min(8, "Password must be at least 8 characters")
  .regex(/[0-9]/, "Password must contain at least one number")
  .regex(/[a-zA-Z]/, "Password must contain at least one letter");

export const Auth = ({ onAuthSuccess }: { onAuthSuccess: () => void }) => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [loading, setLoading] = useState(false);
  const [isSignUp, setIsSignUp] = useState(false);
  const [isForgotPassword, setIsForgotPassword] = useState(false);
  const [challengeSession, setChallengeSession] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const { toast } = useToast();
  const { login: authLogin, respondChallenge: authRespondChallenge } = useAuth();

  const validatePassword = (pwd: string): string | null => {
    try {
      passwordSchema.parse(pwd);
      return null;
    } catch (error) {
      if (error instanceof z.ZodError) {
        return error.errors[0].message;
      }
      return "Invalid password";
    }
  };

  const handleChallengeResponse = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const pwdError = validatePassword(newPassword);
      if (pwdError) throw new Error(pwdError);
      if (newPassword !== confirmNewPassword) throw new Error("Passwords do not match");

      await authRespondChallenge(challengeSession!, email, newPassword);
      setChallengeSession(null);
      toast({ title: "Password updated and signed in successfully" });
      onAuthSuccess();
    } catch (error: any) {
      toast({ title: "Password change failed", description: error.message, variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      if (isForgotPassword) {
        await apiClient.resetPassword(email);
        toast({ title: "Reset email sent", description: "Check your email for the password reset code." });
        setIsForgotPassword(false);
        setEmail("");
      } else if (isSignUp) {
        const pwdError = validatePassword(password);
        if (pwdError) throw new Error(pwdError);
        if (password !== confirmPassword) throw new Error("Passwords do not match");
        if (!acceptTerms) throw new Error("You must accept the terms and privacy policy");

        await apiClient.register(email, password, fullName);
        toast({ title: "Account created", description: "Please check your email to verify your account before signing in." });
        setIsSignUp(false);
        setEmail("");
        setPassword("");
        setConfirmPassword("");
        setFullName("");
        setAcceptTerms(false);
      } else {
        const response = await authLogin(email, password);

        if (response.challenge === "NEW_PASSWORD_REQUIRED") {
          setChallengeSession(response.session);
          toast({ title: "Password update required", description: "Your account was migrated. Please set a new password." });
          return;
        }

        toast({ title: "Signed in successfully" });
        onAuthSuccess();
      }
    } catch (error: any) {
      toast({
        title: isForgotPassword ? "Reset failed" : "Authentication failed",
        description: error.message,
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  if (challengeSession) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6">
        <Card className="w-full max-w-md p-8 bg-gradient-card border-border shadow-card">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-primary rounded-full mb-4">
              <LogIn className="h-8 w-8 text-primary-foreground" />
            </div>
            <h1 className="text-2xl font-bold text-foreground mb-2">Set New Password</h1>
            <p className="text-muted-foreground">Your account was migrated. Please set a new password to continue.</p>
          </div>
          <form onSubmit={handleChallengeResponse} className="space-y-4">
            <Input type="password" placeholder="New Password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required disabled={loading} className="bg-background/50" />
            <p className="text-xs text-muted-foreground">Min 8 characters, 1 number, 1 letter</p>
            <Input type="password" placeholder="Confirm New Password" value={confirmNewPassword} onChange={(e) => setConfirmNewPassword(e.target.value)} required disabled={loading} className="bg-background/50" />
            <Button type="submit" className="w-full" disabled={loading}>{loading ? "Updating..." : "Set Password & Sign In"}</Button>
          </form>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-6">
      <Card className="w-full max-w-md p-8 bg-gradient-card border-border shadow-card">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-primary rounded-full mb-4">
            <LogIn className="h-8 w-8 text-primary-foreground" />
          </div>
          <h1 className="text-2xl font-bold text-foreground mb-2">
            {isForgotPassword ? "Reset Password" : isSignUp ? "Create Account" : "Sign In"}
          </h1>
          <p className="text-muted-foreground">
            {isForgotPassword ? "Enter your email to receive a reset code" : isSignUp ? "Create an account to start analyzing contracts" : "Sign in to access Digestor"}
          </p>
        </div>

        <form onSubmit={handleAuth} className="space-y-4">
          {isSignUp && (<div><Input type="text" placeholder="Full Name" value={fullName} onChange={(e) => setFullName(e.target.value)} required disabled={loading} className="bg-background/50" /></div>)}
          <div><Input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required disabled={loading} className="bg-background/50" /></div>

          {!isForgotPassword && (
            <>
              <div>
                <Input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required disabled={loading} className="bg-background/50" />
                {isSignUp && <p className="text-xs text-muted-foreground mt-1">Min 8 characters, 1 number, 1 letter</p>}
              </div>
              {isSignUp && (<div><Input type="password" placeholder="Confirm Password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required disabled={loading} className="bg-background/50" /></div>)}
              {!isSignUp && (
                <div className="flex items-center space-x-2">
                  <Checkbox id="remember" checked={rememberMe} onCheckedChange={(checked) => setRememberMe(checked as boolean)} disabled={loading} />
                  <Label htmlFor="remember" className="text-sm cursor-pointer">Remember me</Label>
                </div>
              )}
              {isSignUp && (
                <div className="flex items-start space-x-2">
                  <Checkbox id="terms" checked={acceptTerms} onCheckedChange={(checked) => setAcceptTerms(checked as boolean)} disabled={loading} required />
                  <Label htmlFor="terms" className="text-sm cursor-pointer leading-tight">I accept the Terms of Service and Privacy Policy</Label>
                </div>
              )}
            </>
          )}

          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? "Loading..." : isForgotPassword ? "Send Reset Code" : isSignUp ? "Sign Up" : "Sign In"}
          </Button>
        </form>

        <div className="mt-6 space-y-2 text-center">
          {!isForgotPassword && (
            <button type="button" onClick={() => { setIsSignUp(!isSignUp); setPassword(""); setConfirmPassword(""); }} className="text-sm text-muted-foreground hover:text-foreground transition-colors block w-full" disabled={loading}>
              {isSignUp ? "Already have an account? Sign in" : "Don't have an account? Sign up"}
            </button>
          )}
          {!isSignUp && (
            <button type="button" onClick={() => { setIsForgotPassword(!isForgotPassword); setPassword(""); }} className="text-sm text-muted-foreground hover:text-foreground transition-colors block w-full" disabled={loading}>
              {isForgotPassword ? "Back to sign in" : "Forgot password?"}
            </button>
          )}
        </div>
      </Card>
    </div>
  );
};
