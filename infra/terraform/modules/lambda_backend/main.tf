locals {
  state_table_name = "${var.name}-state"
  log_group_name   = "/aws/lambda/${var.name}"

  ssm_secret_arns = [
    for arn in values(var.runtime_secret_arns) : arn
    if strcontains(arn, ":parameter/")
  ]

  secrets_manager_secret_arns = [
    for arn in values(var.runtime_secret_arns) : arn
    if strcontains(arn, ":secret:")
  ]

  secret_reference_environment_variables = {
    for key, arn in var.runtime_secret_arns : "${key}_SECRET_REF" => arn
  }

  reserved_lambda_environment_variable_names = toset([
    "AWS_REGION",
  ])

  sanitized_runtime_environment_variables = {
    for key, value in var.runtime_environment_variables : key => value
    if !contains(local.reserved_lambda_environment_variable_names, key)
  }

  base_environment_variables = {
    APP_ENV                   = var.environment
    AWS_BUCKET_NAME           = var.aws_bucket_name
    STATE_BACKEND             = "dynamodb"
    DYNAMODB_STATE_TABLE_NAME = aws_dynamodb_table.state.name
    DYNAMODB_STATE_KEY_PREFIX = var.state_key_prefix
    SESSION_TTL_SECONDS       = tostring(var.session_ttl_seconds)
    BUFFER_TTL_SECONDS        = tostring(var.buffer_ttl_seconds)
    RATE_LIMIT_TTL_SECONDS    = tostring(var.rate_limit_ttl_seconds)
    LAMBDA_TIMEOUT_SECONDS    = tostring(var.timeout_seconds)
    ALLOWED_CORS_ORIGINS      = var.allowed_cors_origins
    PUBLIC_API_URL            = var.public_api_url != null ? var.public_api_url : ""
    PUBLIC_FRONTEND_URL       = var.public_frontend_url != null ? var.public_frontend_url : ""
    PUBLIC_ADMIN_URL          = var.public_admin_url != null ? var.public_admin_url : ""
  }

  runtime_environment_variables = merge(
    local.base_environment_variables,
    local.secret_reference_environment_variables,
    local.sanitized_runtime_environment_variables,
  )

  execution_role_arn = var.execution_role_arn != null ? var.execution_role_arn : aws_iam_role.lambda[0].arn
}

data "aws_partition" "current" {}

data "aws_caller_identity" "current" {}

resource "aws_dynamodb_table" "state" {
  name                        = local.state_table_name
  billing_mode                = var.state_table_billing_mode
  hash_key                    = "PK"
  range_key                   = "SK"
  deletion_protection_enabled = var.state_table_deletion_protection_enabled

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = var.state_table_point_in_time_recovery_enabled
  }

  tags = merge(var.tags, { Service = "lambda-backend-state" })
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = local.log_group_name
  retention_in_days = var.access_log_retention_days
  tags              = merge(var.tags, { Service = "lambda-backend" })
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigateway/${var.name}"
  retention_in_days = var.access_log_retention_days
  tags              = merge(var.tags, { Service = "lambda-backend-api" })
}

data "aws_iam_policy_document" "assume_lambda" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  count = var.execution_role_arn == null ? 1 : 0

  name                 = var.name
  assume_role_policy   = data.aws_iam_policy_document.assume_lambda.json
  permissions_boundary = var.permissions_boundary_arn
  tags                 = merge(var.tags, { Service = "lambda-backend" })
}

data "aws_iam_policy_document" "lambda_runtime" {
  statement {
    sid = "WriteLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }

  statement {
    sid = "ReadCatalogBucket"
    actions = [
      "s3:GetObject",
    ]
    resources = ["arn:${data.aws_partition.current.partition}:s3:::${var.aws_bucket_name}/*"]
  }

  statement {
    sid       = "ListCatalogBucket"
    actions   = ["s3:ListBucket"]
    resources = ["arn:${data.aws_partition.current.partition}:s3:::${var.aws_bucket_name}"]
  }

  statement {
    sid = "UseStateTable"
    actions = [
      "dynamodb:BatchGetItem",
      "dynamodb:BatchWriteItem",
      "dynamodb:ConditionCheckItem",
      "dynamodb:DeleteItem",
      "dynamodb:DescribeTable",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:Query",
      "dynamodb:UpdateItem",
    ]
    resources = [aws_dynamodb_table.state.arn]
  }

  dynamic "statement" {
    for_each = length(local.ssm_secret_arns) > 0 ? [1] : []
    content {
      sid       = "ReadSsmRuntimeSecrets"
      actions   = ["ssm:GetParameter", "ssm:GetParameters"]
      resources = local.ssm_secret_arns
    }
  }

  dynamic "statement" {
    for_each = length(local.secrets_manager_secret_arns) > 0 ? [1] : []
    content {
      sid       = "ReadSecretsManagerRuntimeSecrets"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = local.secrets_manager_secret_arns
    }
  }

  dynamic "statement" {
    for_each = length(var.kms_key_arns) > 0 ? [1] : []
    content {
      sid       = "DecryptRuntimeSecrets"
      actions   = ["kms:Decrypt"]
      resources = var.kms_key_arns
    }
  }
}

resource "aws_iam_role_policy" "lambda_runtime" {
  count = var.execution_role_arn == null ? 1 : 0

  name   = "${var.name}-runtime"
  role   = aws_iam_role.lambda[0].id
  policy = data.aws_iam_policy_document.lambda_runtime.json
}

resource "aws_lambda_function" "this" {
  function_name = var.name
  role          = local.execution_role_arn
  handler       = var.handler
  runtime       = var.runtime
  filename      = var.lambda_package_path
  publish       = true
  memory_size   = var.memory_size
  timeout       = var.timeout_seconds

  environment {
    variables = local.runtime_environment_variables
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.lambda_runtime,
  ]

  tags = merge(var.tags, { Service = "lambda-backend" })
}

resource "aws_lambda_alias" "this" {
  name             = var.alias_name
  description      = "${var.environment} backend traffic alias"
  function_name    = aws_lambda_function.this.function_name
  function_version = aws_lambda_function.this.version
}

resource "aws_apigatewayv2_api" "this" {
  name          = "${var.name}-http"
  protocol_type = "HTTP"

  cors_configuration {
    allow_headers = ["authorization", "content-type", "x-api-key"]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_origins = split(",", var.allowed_cors_origins)
    max_age       = 300
  }

  tags = merge(var.tags, { Service = "lambda-backend-api" })
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_alias.this.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "root" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "ANY /"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "proxy" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "this" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = var.api_stage_name
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      integrationErr = "$context.integrationErrorMessage"
    })
  }

  tags = merge(var.tags, { Service = "lambda-backend-api" })
}

resource "aws_lambda_permission" "allow_http_api" {
  statement_id  = "AllowExecutionFromHttpApi"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  qualifier     = aws_lambda_alias.this.name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}
