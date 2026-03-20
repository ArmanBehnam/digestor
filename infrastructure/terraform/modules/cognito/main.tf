variable "environment" { type = string }

resource "aws_cognito_user_pool" "main" {
  name = "digestor-w33-users-${var.environment}"

  # Username is email
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # Password policy
  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
    require_uppercase = true
  }

  # Email configuration
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  # Schema
  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  schema {
    name                = "name"
    attribute_data_type = "String"
    required            = true
    mutable             = true

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  schema {
    name                = "role"
    attribute_data_type = "String"
    required            = false
    mutable             = true

    string_attribute_constraints {
      min_length = 1
      max_length = 50
    }
  }

  # Account recovery
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # MFA (optional for prod)
  mfa_configuration = var.environment == "prod" ? "OPTIONAL" : "OFF"

  user_pool_add_ons {
    advanced_security_mode = var.environment == "prod" ? "ENFORCED" : "OFF"
  }
}

# App Client
resource "aws_cognito_user_pool_client" "web" {
  name         = "digestor-w33-web-${var.environment}"
  user_pool_id = aws_cognito_user_pool.main.id

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]

  generate_secret = false  # Public client (SPA)

  access_token_validity  = 1   # hours
  id_token_validity      = 1   # hours
  refresh_token_validity = 30  # days

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  prevent_user_existence_errors = "ENABLED"
}

# User Groups
resource "aws_cognito_user_group" "engineer" {
  name         = "engineer"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Regular engineers who process documents"
}

resource "aws_cognito_user_group" "supervisor" {
  name         = "supervisor"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Supervisors who review and approve projects"
}

resource "aws_cognito_user_group" "admin" {
  name         = "admin"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "System administrators"
}

output "user_pool_id" {
  value = aws_cognito_user_pool.main.id
}

output "client_id" {
  value = aws_cognito_user_pool_client.web.id
}
