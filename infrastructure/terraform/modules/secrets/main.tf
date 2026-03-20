variable "environment" { type = string }

resource "aws_secretsmanager_secret" "api_keys" {
  name        = "digestor-w33/${var.environment}/api-keys"
  description = "API keys for Week33 Digestor agentic pipeline"
}

resource "aws_secretsmanager_secret_version" "api_keys" {
  secret_id = aws_secretsmanager_secret.api_keys.id
  secret_string = jsonencode({
    OPENAI_API_KEY    = "CHANGEME"
    GEMINI_API_KEY    = "CHANGEME"
    ANTHROPIC_API_KEY = "CHANGEME"
    AZURE_API_KEY     = "CHANGEME"
    AZURE_ENDPOINT    = "CHANGEME"
  })
  lifecycle {
    ignore_changes = [secret_string]
  }
}

output "secret_arn" {
  value = aws_secretsmanager_secret.api_keys.arn
}
