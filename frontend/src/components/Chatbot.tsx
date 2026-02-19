import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { ArrowUp, Bot, User } from "lucide-react";
import apiClient from "@/lib/apiClient";
import { useToast } from "@/components/ui/use-toast";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface ChatbotProps {
  documentContext: string;
  processingId: string;
}

export const Chatbot = ({ documentContext, processingId }: ChatbotProps) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { toast } = useToast();

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setIsLoading(true);

    try {
      const data = await apiClient.chatWithDocument(
        processingId,
        userMessage,
        messages
      );

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.response },
      ]);
    } catch (error) {
      console.error("Error calling chat function:", error);
      toast({
        title: "Error",
        description: "Failed to get response. Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-4">
        <Bot className="h-6 w-6 text-primary" />
        <h3 className="text-lg font-semibold">Ask Questions About Your Document</h3>
      </div>

      <Card className="p-4 min-h-[300px] max-h-[500px] overflow-y-auto bg-muted/30">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <p>Ask me anything about the uploaded document or extracted data...</p>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((message, index) => (
              <div
                key={index}
                className={`flex gap-3 ${
                  message.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                {message.role === "assistant" && (
                  <div className="flex-shrink-0">
                    <Bot className="h-6 w-6 text-primary" />
                  </div>
                )}
                <div
                  className={`rounded-lg p-3 max-w-[80%] ${
                    message.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-background border"
                  }`}
                >
                  <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                </div>
                {message.role === "user" && (
                  <div className="flex-shrink-0">
                    <User className="h-6 w-6 text-primary" />
                  </div>
                )}
              </div>
            ))}
            {isLoading && (
              <div className="flex gap-3 justify-start">
                <div className="flex-shrink-0">
                  <Bot className="h-6 w-6 text-primary" />
                </div>
                <div className="rounded-lg p-3 bg-background border">
                  <p className="text-sm text-muted-foreground">Thinking...</p>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </Card>

      <form onSubmit={handleSubmit} className="relative">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type your question here..."
          disabled={isLoading}
          className="pr-12"
        />
        <Button
          type="submit"
          size="icon"
          disabled={!input.trim() || isLoading}
          className="absolute right-1 top-1 h-8 w-8"
        >
          <ArrowUp className="h-4 w-4" />
        </Button>
      </form>
    </div>
  );
};
