import { useState } from "react";
import apiClient from "@/lib/apiClient";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { useToast } from "@/hooks/use-toast";
import { KeyRound } from "lucide-react";
import { z } from "zod";
import { useNavigate, useSearchParams } from "react-router-dom";

const passwordSchema = z
  .string()
  .min(8, "Password must be at least 8 characters")
  .regex(/[0-9]/, "Password must contain at least one number")
  .regex(/[a-zA-Z]/, "Password must contain at least one letter");

export const PasswordReset = () => {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState<"request" | "confirm">("request");
  const { toast } = useToast();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // If email is in URL params, pre-fill and go to confirm step
  useState(() => {
    const emailParam = searchParams.get("email");
    if (emailParam) {
      setEmail(emailParam);
      setStep("confirm");
    }
  });

  const handleRequestReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      await apiClient.resetPassword(email);
      toast({
        title: "Code sent",
        description: "Check your email for the verification code.",
      });
      setStep("confirm");
    } catch (error: any) {
      toast({
        title: "Reset failed",
        description: error.message,
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      passwordSchema.parse(password);

      if (password !== confirmPassword) {
        throw new Error("Passwords do not match");
      }

      await apiClient.confirmReset(email, code, password);

      toast({
        title: "Password updated",
        description: "Your password has been successfully reset.",
      });

      navigate("/");
    } catch (error: any) {
      toast({
        title: "Reset failed",
        description: error.message,
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-6">
      <Card className="w-full max-w-md p-8 bg-gradient-card border-border shadow-card">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-primary rounded-full mb-4">
            <KeyRound className="h-8 w-8 text-primary-foreground" />
          </div>
          <h1 className="text-2xl font-bold text-foreground mb-2">
            {step === "request" ? "Reset Password" : "Set New Password"}
          </h1>
          <p className="text-muted-foreground">
            {step === "request"
              ? "Enter your email to receive a verification code"
              : "Enter the code from your email and your new password"}
          </p>
        </div>

        {step === "request" ? (
          <form onSubmit={handleRequestReset} className="space-y-4">
            <div>
              <Input
                type="email"
                placeholder="Email Address"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={loading}
                className="bg-background/50"
              />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Sending..." : "Send Reset Code"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="w-full"
              onClick={() => navigate("/")}
            >
              Back to Sign In
            </Button>
          </form>
        ) : (
          <form onSubmit={handleConfirmReset} className="space-y-4">
            <div>
              <Input
                type="email"
                placeholder="Email Address"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={loading}
                className="bg-background/50"
              />
            </div>
            <div>
              <Input
                type="text"
                placeholder="Verification Code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                required
                disabled={loading}
                className="bg-background/50"
              />
            </div>
            <div>
              <Input
                type="password"
                placeholder="New Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={loading}
                className="bg-background/50"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Min 8 characters, 1 number, 1 letter
              </p>
            </div>
            <div>
              <Input
                type="password"
                placeholder="Confirm New Password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                disabled={loading}
                className="bg-background/50"
              />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Updating..." : "Update Password"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="w-full"
              onClick={() => setStep("request")}
            >
              Resend Code
            </Button>
          </form>
        )}
      </Card>
    </div>
  );
};
